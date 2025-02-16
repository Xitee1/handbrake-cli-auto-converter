import os
import subprocess
from itertools import chain
from pathlib import Path
import shutil
from flask import Flask, request
import multiprocessing
import threading
from waitress import serve

app = Flask(__name__)
stop_conversion = False
conversion_thread = None
base_dir = None

video_extensions = ["mp4", "mkv", "avi", "mov", "webm", "flv", "mpeg", "mpg", "wmv"]

def convert_videos(input_dir, output_dir, processed_dir, preset_dir):
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
            output_file = output_path / Path(*input_file_relative_path.parent.parts[1:]) / f".tmp_{input_file.stem}.mkv"
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
                move_to_processed_folder(
                    source=input_file,
                    destination=processed_path / Path(*input_file_relative_path.parts[1:]),
                    delete_empty_source_folder = True,
                )

            # Remove empty folders in "input/profile" directory
            delete_empty_folders(quality_folder)

            if stop_conversion:
                print("Conversion process stopped.")
                break
        if stop_conversion:
            break


def move_to_processed_folder(source, destination, delete_empty_source_folder = False):
    # Create same folder structure in processed dir
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
    global base_dir, stop_conversion, conversion_thread
    stop_conversion = False

    def run_conversion():
        print("Starting conversion process.")
        convert_videos(
            input_dir=base_dir / "input",
            output_dir=base_dir / "output",
            processed_dir=base_dir / "processed",
            preset_dir=base_dir / "presets",
        )
        print("Conversion process ended.")

    conversion_thread = multiprocessing.Process(target=run_conversion)
    conversion_thread.start()

    return "Starting conversion process."

@app.route('/api/stop', methods=['POST'])
def stop():
    global stop_conversion, conversion_thread
    stop_conversion = True

    force = request.args.get('force', 'false').lower() == 'true'
    if force:
        if conversion_thread is not None:
            conversion_thread.terminate()
            conversion_thread = None
            print("Conversion force-stopped.")
            return "Conversion force-stopped."
        else:
            print("No conversion process to stop.")
            return "No conversion process to stop."

    else:
        print("Stopping conversion process after finishing current task.")
        return "Stopping conversion process after finishing current task."

def run_flask():
    serve(app, host="0.0.0.0", port=5000)

if __name__ == "__main__":
    base_dir = Path(__file__).parent
    print(f"Base dir: {base_dir}")

    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()

    print("Converter is ready. Call POST http://localhost:5000/api/start to start the conversion process.")

