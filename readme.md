# HandBrake-CLI auto converter

A simple python script that converts all video files in a directory to a specified format using HandBrake-CLI.

## Explanation
This simple program can convert all video files from an `input` folder and outputs the converted file in an `output` folder.
While converting, the output file is prefixed with `.tmp_` to make it easy to differentiate between interrupted attempts.
After successful conversion, the file will be renamed back to its original name and the source file from the input file is moved into a separated `processed` folder.

## Features
- **REST-API**
  - After starting the script, it will idle until a start request is sent.
  - Of course, you can also send a stop request. By default, it will finish the current task. It's also possible to force stop directly.
- **Supports multiple Handbrake Presets**: Use all the power of Handbrake
- Output currently only supports `.mkv`

## REST API

| Endpoint               | Description                                                                                                  |
|------------------------|--------------------------------------------------------------------------------------------------------------|
| `/api/start`           | Starts processing all files in the input folder                                                              |
| `/api/stop`            | Finishes the current file and then stops                                                                     |
| `/api/stop?force=true` | Force-stops the processing. An unfinished file with the prefix `.tmp_` will be left in the output directory. |

### TODO
- Add status endpoint
- Add authentication if this project will ever gets attention and there are users that need it

### Why REST API?
It allows you to very simply automate start/stopping.
For example, you can call this API from Home Assistant to start the conversion whenever there's excess solar power.
If you want to fully shut down the PC when no conversion is running, you can use Wake on LAN and configure the script to run on startup (e.g. with @reboot cronjob).
An API endpoint for the current state (if a task is running) will be added soon to also be able to automate the shutdown of the PC.

## Install
- Download the `convert.py`
- Make sure these packages are installed on your system: `python3-flask python3-waitress`.
- Manually create a folder structure like in the example below. Currently, it doesn't get automatically generated and the folder names `input`, `output`, `processed` and `presets`are hardcoded.

## Usage
1. Create a handbrake preset (using Handbrake GUI on your PC) and export it
2. Put this preset into the `presets` folder
3. Create a sub-folder inside the `input` folder named exactly the same as the preset filename in the `presets` folder (without file extension).
4. Put your source files into the `input/presetname` folder
5. Start the program with `python3 convert.py`. The API is now accessible at: `http://x.x.x.x:5000/`
6. To start the conversion, please refer to [REST API](#rest-api)

You can add as many presets as you want. The corresponding preset will be used for processing depending on which sub-folder of `input` you put your files in.

Currently, it is only supported to start the conversion through the API. You can use tools like `Postman` or `curl` for this.

Example: `curl -X POST http://127.0.0.1:5000/api/start`

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
    │   └── preset.json
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
    │   └── preset.json
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
    │   └── preset.json
    └── convert.py
```