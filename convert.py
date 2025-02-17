import os
import subprocess
from itertools import chain
from pathlib import Path
import shutil
from flask import Flask, request, jsonify
import multiprocessing
import threading
from waitress import serve
import argparse

app = Flask(__name__)

conversion_manager = None

video_extensions = ["mp4", "mkv", "avi", "mov", "webm", "flv", "mpeg", "mpg", "wmv"]


def delete_empty_folders(root_folder):
    for dirpath, dirnames, filenames in os.walk(root_folder, topdown=False):
        for dirname in dirnames:
            full_path = os.path.join(dirpath, dirname)
            if not os.listdir(full_path):
                os.rmdir(full_path)


def move_file(source, destination, make_missing_dirs=False):
    if make_missing_dirs:
        destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))


class ConversionManager:
    def __init__(
            self,
            input_dir: str|Path,
            output_dir: str|Path,
            processed_dir: str|Path,
            preset_dir: str|Path,
            output_extension: str|Path,
    ):
        self.input_folder_path = Path(input_dir)
        self.output_folder_path = Path(output_dir)
        self.processed_folder_path = Path(processed_dir)
        self.preset_folder_path = Path(preset_dir)
        self.output_file_extension = output_extension

        self.stop_conversion = False

        # States
        self.conversion_thread = None
        self.conversion_running = False
        self.current_file = None
        self.source_files_total = 0
        self.source_files_processed = 0
        self.source_files_successful = 0
        self.source_files_failed = 0

    def find_input_videos(self) -> list[Path]:
        return list(chain.from_iterable(self.input_folder_path.rglob(f"*.{ext}") for ext in video_extensions))

    def convert_all_videos(self):
        self.conversion_running = True

        if not self.input_folder_path.exists() or not self.preset_folder_path.exists():
            print("Error: Input or preset directory does not exist.")
            return

        source_files = self.find_input_videos()
        self.source_files_total = len(source_files)

        print(f"Found {self.source_files_total} total files to process.")

        for source_path in source_files:
            # Get preset folder & check if it is an directory
            source_preset_folder: Path = self.input_folder_path / source_path.relative_to(self.input_folder_path).parts[0]
            source_preset_name = source_preset_folder.name
            if not source_preset_folder.is_dir():
                print(f"Error: Preset folder '{source_preset_folder}' is not a folder!")
                return

            # Build the paths for the output file
            source_file_relative_folder_path = Path(*source_path.relative_to(self.input_folder_path).parent.parts[1:])
            output_file = self.output_folder_path / source_preset_name / source_file_relative_folder_path / f".tmp_{source_path.stem}.{self.output_file_extension}"
            output_file.parent.mkdir(parents=True, exist_ok=True)

            # Find the preset file
            preset_path = self.preset_folder_path / f"{source_preset_name}.json"

            # Convert the video
            self.convert_video(
                source_path=source_path,
                destination_path=output_file,
                processed_path=self.processed_folder_path / source_preset_name / source_file_relative_folder_path / source_path.name,
                preset_path=preset_path,
                source_preset_name=source_preset_name
            )

            # Remove empty folders in "input/{profileName}" directory
            delete_empty_folders(source_preset_folder)

            # Stop conversion if requested
            if self.stop_conversion:
                print("Conversion process stopped. Conversions left: ", self.source_files_total - self.source_files_successful)
                break

        self.current_file = None
        #self.source_files_total -= self.source_files_successful
        self.source_files_total = 0
        self.source_files_processed = 0
        self.source_files_successful = 0
        self.source_files_failed = 0
        self.conversion_running = False

    def convert_video(
            self,
            source_path: Path,
            destination_path: Path,
            processed_path: Path,
            preset_path: Path,
            source_preset_name: str,
    ):
        self.source_files_processed += 1
        self.current_file = source_path

        # Print status message
        print(f"Processing [{self.source_files_processed}/{self.source_files_total}]: {source_path} -> {destination_path}")

        # Check if preset file exists
        if not preset_path.exists():
            print(f"Warning: No preset file found for {source_preset_name}, skipping.")
            return

        # HandbrakeCLI command
        command = [
            "HandBrakeCLI",
            "--input", str(source_path),
            "--output", str(destination_path),
            "--preset-import-file", str(preset_path),
            "--preset", source_preset_name
        ]

        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            self.source_files_failed += 1
            print(f"Error processing file {source_path}: {result.stderr.decode()}")
        else:
            # Move source file to "processed" directory
            move_file(
                source=source_path,
                destination=processed_path,
                make_missing_dirs=True,
            )

            # Rename output file to remove ".tmp_" prefix
            destination_path.rename(destination_path.with_name(destination_path.name.replace(".tmp_", "")))

            self.source_files_successful += 1
            print(f"Successfully converted {source_path}")


@app.route('/api/start', methods=['POST'])
def start():
    if conversion_manager.conversion_running:
        return "Conversion process is already running."

    conversion_manager.stop_conversion = False

    def run_conversion():
        print("Starting conversion process.")
        conversion_manager.convert_all_videos()
        print("Conversion process ended.")

    conversion_manager.conversion_thread = multiprocessing.Process(target=run_conversion)
    conversion_manager.conversion_thread.start()

    return "Starting conversion process."

@app.route('/api/stop', methods=['POST'])
def stop():
    if conversion_manager.conversion_running:
        conversion_manager.stop_conversion = True
        force = request.args.get('force', 'false').lower() == 'true'
        if force:
            if conversion_manager.conversion_thread is not None:
                conversion_manager.conversion_thread.terminate()
                conversion_manager.conversion_thread = None
                print("Conversion force-stopped.")
                return "Conversion force-stopped."
            else:
                return "No conversion process to stop."
        else:
            print("Stopping conversion process after finishing current task.")
            return "Stopping conversion process after finishing current task."
    else:
        return "No conversion process to stop."

@app.route('/api/status', methods=['GET'])
def status():
    return jsonify({
        "status": "running" if conversion_manager.conversion_running else "idle",
        "scheduled_stop": conversion_manager.stop_conversion,
        "current_file": str(conversion_manager.current_file) if conversion_manager.current_file else None,
        "source_files_total": conversion_manager.source_files_total,
        "source_files_processed": conversion_manager.source_files_processed,
        "source_files_successful": conversion_manager.source_files_successful,
        "source_files_failed": conversion_manager.source_files_failed,
    })

def run_flask(host, port):
    serve(app, host=host, port=port)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="Handbrake Helper")

    parser.add_argument('--force-start', default=False, help="Start the conversion process immediately without waiting for API request.")
    parser.add_argument('--base-dir', default=Path(__file__).parent, help="Base directory for input, output, processed and preset folders.")
    parser.add_argument('--output-extension', default="mkv", help="Output file extension (e.g. mkv, mp4")
    parser.add_argument('--port', default=5000)
    parser.add_argument('--host', default="0.0.0.0")
    args = parser.parse_args()

    base_dir = Path(args.base_dir)
    output_file_extension = args.output_extension

    print(f"Base dir: {base_dir}")

    conversion_manager = ConversionManager(
        input_dir=base_dir / "input",
        output_dir=base_dir / "output",
        processed_dir=base_dir / "processed",
        preset_dir=base_dir / "presets",
        output_extension=output_file_extension,
    )

    flask_thread = threading.Thread(target=run_flask, args=(args.host, int(args.port)))
    flask_thread.start()

    print(f"Handbrake Helper is ready. Call POST http://127.0.0.1:{args.port}/api/start to start the conversion process.")

