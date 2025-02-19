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
import re
from jinja2 import Template
import logging

logger = logging.getLogger(__name__)
app = Flask(__name__)

video_extensions = ["mp4", "mkv", "avi", "mov", "webm", "flv", "mpeg", "mpg", "wmv"]

##################
### CONVERSION ###
##################
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


def find_compatible_files(folder) -> list[Path]:
    return list(chain.from_iterable(folder.rglob(f"*.{ext}") for ext in video_extensions))


def read_text_file(file_path: Path) -> str | None:
    if file_path.exists():
        with open(file_path, 'r') as f:
            return f.read().strip()
    return None


class ConversionManager:
    def __init__(self):
        self.stop_conversion = False

        # Status
        self.conversion_thread = None
        self.conversion_running = False
        self.current_file = None
        self.source_files_total = 0
        self.source_files_processed = 0
        self.source_files_successful = 0
        self.source_files_failed = 0

    def convert_all_videos(
            self,
            input_dir: str | Path,
            output_dir: str | Path,
            processed_dir: str | Path,
            preset_dir: str | Path,
            output_extension: str | Path,
    ):
        self.conversion_running = True

        input_folder_path = Path(input_dir)
        output_folder_path = Path(output_dir)
        processed_folder_path = Path(processed_dir)
        preset_folder_path = Path(preset_dir)
        output_file_extension = output_extension

        if not input_folder_path.exists() or not preset_folder_path.exists():
            logger.error("Error: Input or preset directory does not exist.")
            return

        source_files = find_compatible_files(folder=input_folder_path)
        self.source_files_total = len(source_files)

        logger.info(f"Found {self.source_files_total} total files to process.")

        for source_path in source_files:
            # Get preset folder & check if it is an directory
            source_preset_folder: Path = input_folder_path / source_path.relative_to(input_folder_path).parts[0]
            preset_name = source_preset_folder.name
            if not source_preset_folder.is_dir():
                logger.error(f"Error: Preset folder '{source_preset_folder}' is not a folder!")
                return

            # Build the paths for the output file
            source_file_relative_folder_path = Path(*source_path.relative_to(input_folder_path).parent.parts[1:])
            output_file = output_folder_path / preset_name / source_file_relative_folder_path / f".tmp_{source_path.stem}.{output_file_extension}"
            output_file.parent.mkdir(parents=True, exist_ok=True)

            # Find the preset file
            preset_path = preset_folder_path / f"{preset_name}.json"

            # Find extra config files
            individual_config = read_text_file(source_path.with_suffix('.hbconf'))
            global_config = read_text_file(source_path.parent / '_.hbconf')

            # Prefer individual config over global
            extra_options = individual_config if individual_config is not None else global_config

            # Convert the video
            self.convert_video(
                source_path=source_path,
                destination_path=output_file,
                processed_path=processed_folder_path / preset_name / source_file_relative_folder_path / source_path.name,
                preset_path=preset_path,
                preset_name=preset_name,
                extra_options=extra_options,
            )

            # Remove empty folders in "input/{profileName}" directory
            delete_empty_folders(source_preset_folder)

            # Stop conversion if requested
            if self.stop_conversion:
                logger.info("Conversion process stopped. Conversions left: ", self.source_files_total - self.source_files_successful)
                break

        self.current_file = None
        #self.source_files_total -= self.source_files_successful
        self.source_files_total = 0
        self.source_files_processed = 0
        self.source_files_successful = 0
        self.source_files_failed = 0
        self.conversion_running = False


    def scan_video(self, source_path: Path, preset_path: Path = None, preset_name: str = None) -> str | None:
        """
        Scan a video file using HandbrakeCLI and returns the output.

        Parameters preset_path and preset_name must be used together!

        :param source_path: Path to the source file
        :param preset_path: Path to the preset file (optional)
        :param preset_name: Preset name (optional)
        :return: Output of HandBrakeCLI
        """
        # HandbrakeCLI command
        command = [
            "HandBrakeCLI",
            "--input", str(source_path),
            "--scan"
        ]

        if preset_path and preset_name:
            command.extend([
                "--preset-import-file", str(preset_path),
                "--preset", preset_name,
            ])

        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            logger.error(f"Unable to scan file {source_path}: {result.stderr.decode()}")
            return None
        else:
            logger.info(f"Successfully scanned {source_path}")
        return result.stderr.decode()


    def convert_video(
            self,
            source_path: Path,
            destination_path: Path,
            processed_path: Path,
            preset_path: Path,
            preset_name: str,
            extra_options: str = None,
            pre_scan: bool = True
    ):
        """
        Convert a video file using HandbrakeCLI.

        :param source_path: The path to the source file
        :param destination_path: The path to save the converted file to
        :param processed_path: The path to move the source file to after conversion
        :param preset_path: The path to the preset file
        :param preset_name: The name of the preset to use
        :param extra_options: String of extra options to be appended to the HandBrakeCLI command
        :param pre_scan: Required if using jinja2 templating in extra options
        :return:
        """

        self.source_files_processed += 1
        self.current_file = source_path

        # Show progress message
        logger.info(f"Processing [{self.source_files_processed}/{self.source_files_total}]: {source_path} -> {destination_path}")

        # Check if preset file exists
        if not preset_path.exists():
            logger.warning(f"Warning: No preset file found for {preset_name}, skipping.")
            return

        if pre_scan:
            scan_result = self.scan_video(
                source_path=source_path,
                preset_path=preset_path,
                preset_name=preset_name,
            )
            if scan_result is None:
                logger.warning(f"Warning: Could not scan file {source_path}, skipping.")
                return

            chapter_amount = len(re.findall(r"\+ (\d+): duration ", scan_result))

            extra_options = Template(extra_options).render(
                video={
                    "chapter_amount": chapter_amount
                }
            )

        # HandbrakeCLI command
        command = [
            "HandBrakeCLI",
            "--input", str(source_path),
            "--output", str(destination_path),
            "--preset-import-file", str(preset_path),
            "--preset", preset_name,
        ]

        if extra_options:
            command.extend(extra_options.split())

        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            self.source_files_failed += 1
            logger.error(f"Error processing file {source_path}: {result.stderr.decode()}")
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
            logger.info(f"Successfully converted {source_path}")


################
### REST API ###
################
@app.route('/api/start', methods=['POST'])
def start():
    if conversion_manager.conversion_running:
        return "Conversion process is already running."

    conversion_manager.stop_conversion = False

    def run_conversion():
        logger.info("Starting conversion process.")
        conversion_manager.convert_all_videos(
            input_dir=_BASE_DIR / "input",
            output_dir=_BASE_DIR / "output",
            processed_dir=_BASE_DIR / "processed",
            preset_dir=_BASE_DIR / "presets",
            output_extension=_OUTPUT_FILE_EXTENSION,
        )
        logger.info("Conversion process ended.")

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
                logger.warning("Conversion force-stopped.")
                return "Conversion force-stopped."
            else:
                return "No conversion process to stop."
        else:
            logger.info("Stopping conversion process after finishing current task.")
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


############
### MAIN ###
############
conversion_manager = ConversionManager()
if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="Handbrake Helper")

    parser.add_argument('--log-level', default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help="Set the logging level")
    parser.add_argument('--force-start', default=False, help="Start the conversion process immediately without waiting for API request.")
    parser.add_argument('--base-dir', default=Path(__file__).parent, help="Base directory for input, output, processed and preset folders.")
    parser.add_argument('--output-extension', default="mkv", help="Output file extension (e.g. mkv, mp4")
    parser.add_argument('--port', default=5000)
    parser.add_argument('--host', default="0.0.0.0")
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper()))
    _BASE_DIR = Path(args.base_dir)
    _OUTPUT_FILE_EXTENSION = args.output_extension

    logger.info(f"Base dir: {_BASE_DIR}")

    flask_thread = threading.Thread(target=run_flask, args=(args.host, int(args.port)))
    flask_thread.start()

    logger.info(f"Handbrake Helper is ready. Call POST http://127.0.0.1:{args.port}/api/start to start the conversion process.")

