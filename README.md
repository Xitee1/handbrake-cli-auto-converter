# HandBrake-CLI auto converter

This simple program converts all video files from an `input` folder and outputs the converted file in an `output` folder using HandBrakeCLI.
After successful conversion, the original source file placed into a separated `processed` folder to prevent it from getting converted again in the next run.

It's very similar to `docker-handbrake` or other tools like `unmanic` but without GUI and is made to be as simple as possible.
You can create presets in the Handbrake GUI on Desktop and add these presets to the `presets` folder.
Based on which subfolder inside of `input` you place your files, a different preset is being used.
It's controlled through a very simple REST API.

**It should fit your needs perfectly if you are used to adding hundreds of files to your handbrake queue and want to automate that.** 

## Features
- **REST-API**
  - Fully controllable through the API for better automation
- **Supports multiple Handbrake Presets**:
  - Use all the power of Handbrake
- **Temporary filenames**:
  - Normally it's hard to tell if a handbrake task was finished successfully because the output file looks normal at the first look. Using temporary filenames, you can easily tell if the conversion was successfully finished.
- **Stop/Resume batch**:
  - When stopping the process using the API, it will finish the current file and then stop. On the next start it will resume the rest of the files. **NOTE:** It's not possible to pause mid-file!
  - If interrupted, it leaves behind an unfinished file with the prefix `.tmp_` in the output folder. This file can't be resumed but will be restarted the next time.

## TODO
- Add API status endpoint
- Docker image + Proxmox LXC template
- Add authentication if this project will ever gets attention and there are users that need it

## REST API
| Endpoint               | Description                                                                                                   |
|------------------------|---------------------------------------------------------------------------------------------------------------|
| `/api/start`           | Starts processing all files in the input folder                                                               |
| `/api/stop`            | Finishes the current file and then stops                                                                      |
| `/api/stop?force=true` | Interrupts the process immediately. The unfinished file can't be resumed but will be restarted the next time. |
| `/api/status`          | Example output: `{"current_file":null,"scheduled_stop":false,"source_files_failed":null,"source_files_processed":null,"source_files_successful":null,"source_files_total":null,"status":"idle"}`                                                                                              |

### Why REST API?
It allows you to very simply automate start/stopping.
For example, you can call this API from Home Assistant to start the conversion whenever there's excess solar power.
If you want to fully shut down the PC when no conversion is running, you can use Wake on LAN and configure the script to run on startup (using a cronjob or [run as systemd service](#run-as-systemd-service)).
To shut down the PC, you can use the status endpoint to check if a conversion is currently running.

## Installation
- Download the `convert.py` file from [Releases](https://github.com/Xitee1/handbrake-cli-auto-converter/releases)
- Make sure these packages are installed on your system: `handbrake-cli python3-flask python3-waitress`
- Manually create a folder structure [like this](#example-folder-structure). Currently, it doesn't get automatically generated and the folder names `input`, `output`, `processed` and `presets`are hardcoded.
- Optional: [Run as systemd service](#run-as-systemd-service)

## Usage
1. Start the program your preferred way (e.g. `python3 convert.py`). The API is now accessible at: `http://x.x.x.x:5000/`
2. Create a handbrake preset (using Handbrake GUI on your PC) and export it (**Preset filename AND preset displayname must match! Currently only one preset per export file is supported!**)
3. Place your presets into the `presets` folder
4. Create a sub-folder inside of `input` named exactly the same as your preset
5. Put your source files into the `input/presetName` folder
6. To start the conversion, please refer to [REST API](#rest-api)

You can add as many presets as you want. The corresponding preset will be used for your files depending on which sub-folder inside of `input` they are.

By default, the program will idle after startup and wait for a start request.
However, there are some options that you can use. Check them out with `python3 convert.py --help`

## Run as systemd service
To run the program without leaving the terminal open and automatically on startup, you can create a systemd service.

1. `nano /etc/systemd/system/handbrake-helper.service`
2. Insert this and adjust `WorkingDirectory` and `ExecStart` to match your paths:
```ini
[Unit]
Description=Handbrake helper
After=network.target

[Service]
ExecStart=/usr/bin/python3 /mnt/convert/convert.py
WorkingDirectory=/mnt/convert
StandardOutput=append:/var/log/handbrake-helper.log
StandardError=append:/var/log/handbrake-helper.err.log
Restart=always
User=user
Group=user

[Install]
WantedBy=multi-user.target
```
3. `systemctl daemon-reload`
4. `systemctl enable handbrake-helper.service`
5. `systemctl start handbrake-helper.service`
6. `systemctl status handbrake-helper.service`

## Example folder structure
Before conversion:
```
.
└── convert/
    ├── input/
    │   └── preset1/
    │       └── something.S01/
    │           ├── something.S01E01.mp4
    │           └── something.S01E02.mp4
    ├── output
    ├── processed
    ├── presets/
    │   └── preset1.json
    └── convert.py
```

Mid-conversion:
```
.
└── convert/
    ├── input/
    │   └── preset1/
    │       └── something.S01/
    │           └── something.S01E02.mp4
    ├── output/
    │   └── something.S01/
    │       ├── something.S01E01.mkv
    │       └── .tmp_something.S01E02.mkv
    ├── processed/
    │   └── something.S01/
    │       └── something.S01E01.mp4
    ├── presets/
    │   └── preset1.json
    └── convert.py
```

After conversion:
```
.
└── convert/
    ├── input/
    │   └── preset1
    ├── output/
    │   └── something.S01/
    │       ├── something.S01E01.mkv
    │       └── something.S01E02.mkv
    ├── processed/
    │   └── something.S01/
    │       ├── something.S01E01.mp4
    │       └── something.S01E02.mp4
    ├── presets/
    │   └── preset1.json
    └── convert.py
```

## Advanced Handbrake Options
You can add custom HandBrakeCLI options to the command by creating specifically named files in the input folder.
There are 2 options:
1. Use a file called `_.hbconf` that applies to all files at the same directory (in the future nested directories might be supported too)
2. Use a file called exactly like a specific video file with the `.hbconf` extension to only apply the options for a specific file

In this file, you simply write the additional options as plain text.
Example: `--chapters 1-5`

_NOTE: Currently the `_.hbconf` file does not work for nested directories! It must be on the same level as your video files._

See the handbrake documentation for all available options:
https://handbrake.fr/docs/en/latest/cli/command-line-reference.html
