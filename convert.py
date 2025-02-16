import os
import subprocess
from pathlib import Path
import shutil

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
        
        input_files = list(quality_folder.rglob("*.mkv"))  # Modify for other formats if needed

        for input_file in input_files:
            input_file_relative_path = input_file.relative_to(input_path)
            output_file = output_path / Path(*input_file_relative_path.parent.parts[1:]) / f"{input_file.stem}-dasdasd.mkv"
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            print(f"Converting: {input_file_relative_path} -> {output_file}")
            
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


if __name__ == "__main__":
    BASE_DIR = Path(__file__).parent
    print(f"Base dir: {BASE_DIR}")
    convert_videos(
        input_dir = BASE_DIR / "input",
        output_dir = BASE_DIR / "output",
        processed_dir = BASE_DIR / "processed",
        preset_dir = BASE_DIR / "presets",
    )

