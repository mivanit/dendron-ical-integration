scrapes [Dendron](https://www.dendron.so) events from a vault, outputs them to ical, markdown, json, or jsonl

content will be read from the input (second argument), processed with the optional specified config (third argument), and output to stdout in the format (first argument)

input can be either a python glob-parseable pattern, or a json/jsonl file (produced by this script)

# Usage

usage options:
```bash
	py make_cal.py <output_fmt> <input_path>
	py make_cal.py <output_fmt> <input_path> [config]
	py make_cal.py <output_fmt> --path=<input> --cfg_path[config]
```

writing to the file should be done via a shell redirect, for example:
```bash
	py make_cal.py ical /path/to/dendron/vault > cal.ics
```

# Setup

I reccomend setting up a bash script (see `run_all.sh`) to run this script regularly on your Dendron vault, and then upload the resulting ical file somewhere.

I do this by having the script place the ical file into a folder that is synced to Google drive, which then automatically uploads the file which can be viewed via a shared link.

Note: Google calendar only pulls from the ical link you give it once every day or so, and there is unfortunately no option to force it to update. I use [GAS-ICS-Sync](https://github.com/derekantrican/GAS-ICS-Sync) to get around this, its quite easy to set up.


# Info

ical file format spec: https://datatracker.ietf.org/doc/html/rfc5545

by [Michael Ivanitskiy](https://mivanit.github.io)