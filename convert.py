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

class ConversionManager:
    def __init__(self, input_dir, output_dir, processed_dir, preset_dir, output_extension):
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


    def convert_videos(self):
        self.conversion_running = True

        if not self.input_folder_path.exists() or not self.preset_folder_path.exists():
            print("Error: Input or preset directory does not exist.")
            return

        source_files = list(chain.from_iterable(self.input_folder_path.rglob(f"*.{ext}") for ext in video_extensions))
        self.source_files_total = len(source_files)

        print(f"Found {self.source_files_total} total files to process.")

        for source_file in source_files:
            self.source_files_processed += 1
            self.current_file = source_file

            # Get preset folder & check if it is an directory
            source_preset_folder: Path = self.input_folder_path / source_file.relative_to(self.input_folder_path).parts[0]
            source_preset_name = source_preset_folder.name
            if not source_preset_folder.is_dir():
                print(f"Warning: Preset folder '{source_preset_folder}' is not a folder!")
                continue

            # Build the paths for the output file
            source_file_relative_folder_path = Path(*source_file.relative_to(self.input_folder_path).parent.parts[1:])
            output_file = self.output_folder_path / source_file_relative_folder_path / f".tmp_{source_file.stem}.{self.output_file_extension}"
            output_file.parent.mkdir(parents=True, exist_ok=True)

            # Print status message
            print(f"Processing [{self.source_files_processed}/{self.source_files_total}]: {source_file} -> {output_file}")

            # Find the preset file and check if it exists
            preset_file = self.preset_folder_path / f"{source_preset_name}.json"
            if not preset_file.exists():
                print(f"Warning: No preset file found for {source_preset_name}, skipping.")
                continue

            # HandbrakeCLI command
            command = [
                "HandBrakeCLI",
                "--input", str(source_file),
                "--output", str(output_file),
                "--preset-import-file", str(preset_file),
                "--preset", source_preset_name
            ]

            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode != 0:
                self.source_files_failed += 1
                print(f"Error processing file {source_file}: {result.stderr.decode()}")
            else:
                # Move source file to "processed" directory
                self.move_file(
                    source=source_file,
                    destination=self.processed_folder_path / source_file_relative_folder_path / source_file.name,
                    make_missing_dirs=True,
                )

                # Rename output file to remove ".tmp_" prefix
                output_file.rename(output_file.with_name(output_file.name.replace(".tmp_", "")))

                self.source_files_successful += 1
                print(f"Successfully converted {source_file}")

            # Remove empty folders in "input/{profileName}" directory
            self.delete_empty_folders(source_preset_folder)

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

    def move_file(self, source, destination, make_missing_dirs=False):
        if make_missing_dirs:
            destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))

    def delete_empty_folders(self, root_folder):
        for dirpath, dirnames, filenames in os.walk(root_folder, topdown=False):
            for dirname in dirnames:
                full_path = os.path.join(dirpath, dirname)
                if not os.listdir(full_path):
                    os.rmdir(full_path)


@app.route('/api/start', methods=['POST'])
def start():
    if conversion_manager.conversion_running:
        return "Conversion process is already running."

    conversion_manager.stop_conversion = False

    def run_conversion():
        print("Starting conversion process.")
        conversion_manager.convert_videos(

        )
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

