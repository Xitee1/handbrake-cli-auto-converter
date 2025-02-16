import os
import subprocess
from itertools import chain
from pathlib import Path
import shutil
from flask import Flask, request
import multiprocessing
import threading
from waitress import serve
import argparse

app = Flask(__name__)
stop_conversion = False
conversion_thread = None
conversion_running = False

output_extension = None
base_dir = None

video_extensions = ["mp4", "mkv", "avi", "mov", "webm", "flv", "mpeg", "mpg", "wmv"]

def convert_videos(input_dir, output_dir, processed_dir, preset_dir, output_file_extension):
    global conversion_running

    conversion_running = True
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    processed_path = Path(processed_dir)
    preset_path = Path(preset_dir)
    
    if not input_path.exists() or not preset_path.exists():
        print("Error: Input or preset directory does not exist.")
        return
    
    for quality_folder in input_path.iterdir():
        if not quality_folder.is_dir():
            continue
        
        preset_file = preset_path / f"{quality_folder.name}.json"
        if not preset_file.exists():
            print(f"Warning: No preset file found for {quality_folder.name}, skipping.")
            continue

        input_files = list(chain.from_iterable(quality_folder.rglob(f"*.{ext}") for ext in video_extensions))
        input_file_amount = len(input_files)
        print(f"Found {input_file_amount} files to process for profile {quality_folder.name}.")

        for index, input_file in enumerate(input_files, start=1):
            input_file_relative_path = input_file.relative_to(input_path)
            output_file = output_path / Path(*input_file_relative_path.parent.parts[1:]) / f".tmp_{input_file.stem}.{output_file_extension}"
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            print(f"Converting [{index}/{input_file_amount}]: {input_file} -> {output_file}")
            
            command = [
                "HandBrakeCLI",
                "--input", str(input_file),
                "--output", str(output_file),
                "--preset-import-file", str(preset_file),
                "--preset", quality_folder.name
            ]
            
            #with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as process:
            #    for line in process.stdout:
            #        print(line.decode('utf8'))

            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode != 0:
                print(f"Error converting {input_file_relative_path}: {result.stderr.decode()}")
            else:
                print(f"Successfully converted {input_file_relative_path}")

                # Move source file to "processed" directory
                move_file(
                    source=input_file,
                    destination=processed_path / Path(*input_file_relative_path.parts[1:]),
                    make_missing_dirs = True,
                )

                # Rename output file to remove ".tmp_" prefix
                output_file.rename(output_file.with_name(output_file.name.replace(".tmp_", "")))

            # Remove empty folders in "input/profile" directory
            delete_empty_folders(quality_folder)

            if stop_conversion:
                print("Conversion process stopped.")
                break
        if stop_conversion:
            print("Conversion process stopped.")
            break

    conversion_running = False

def move_file(source, destination, make_missing_dirs = False):
    if make_missing_dirs:
        destination.parent.mkdir(parents=True, exist_ok=True)

    shutil.move(str(source), str(destination))


def delete_empty_folders(root_folder):
    for dirpath, dirnames, filenames in os.walk(root_folder, topdown=False):
        for dirname in dirnames:
            full_path = os.path.join(dirpath, dirname)
            if not os.listdir(full_path):
                os.rmdir(full_path)

@app.route('/api/start', methods=['POST'])
def start():
    global stop_conversion, conversion_thread

    if conversion_running:
        return "Conversion process is already running."

    stop_conversion = False

    def run_conversion():
        print("Starting conversion process.")
        convert_videos(
            input_dir=base_dir / "input",
            output_dir=base_dir / "output",
            processed_dir=base_dir / "processed",
            preset_dir=base_dir / "presets",
            output_file_extension=output_extension,
        )
        print("Conversion process ended.")

    conversion_thread = multiprocessing.Process(target=run_conversion)
    conversion_thread.start()

    return "Starting conversion process."

@app.route('/api/stop', methods=['POST'])
def stop():
    global stop_conversion, conversion_thread

    if conversion_running:
        stop_conversion = True
        force = request.args.get('force', 'false').lower() == 'true'
        if force:
            if conversion_thread is not None:
                conversion_thread.terminate()
                conversion_thread = None
                print("Conversion force-stopped.")
                return "Conversion force-stopped."
            else:
                return "No conversion process to stop."

        else:
            print("Stopping conversion process after finishing current task.")
            return "Stopping conversion process after finishing current task."
    else:
        return "No conversion process to stop."

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
    output_extension = args.output_extension

    print(f"Base dir: {base_dir}")

    flask_thread = threading.Thread(target=run_flask, args=(args.host, int(args.port)))
    flask_thread.start()

    print(f"Handbrake Helper is ready. Call POST http://127.0.0.1:{args.port}/api/start to start the conversion process.")

