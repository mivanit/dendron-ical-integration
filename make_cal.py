"""scrape dendron events from a vault, outputs them to ical, markdown, json, or jsonl

content will be read from the input (second argument), processed with the optional specified config (third argument), and output to stdout in the format (first argument)

input can be either a python glob-parseable pattern, or a json/jsonl file (produced by this script)

usage options:
	python3 make_cal.py <output_fmt> <input_path>
	python3 make_cal.py <output_fmt> <input_path> [config]
	python3 make_cal.py <output_fmt> --path=<input> --cfg_path[config]

writing to the file should be done via a shell redirect, for example:
	python3 make_cal.py ical /path/to/dendron/vault > cal.ics

ical file format spec: https://datatracker.ietf.org/doc/html/rfc5545

by [Michael Ivanitskiy](https://mivanit.github.io)
"""

from dataclasses import dataclass
from functools import partial
import json
import os
from pathlib import Path
import sys
from typing import Callable, Literal
from datetime import datetime, timedelta, date, time
import re
import glob
import warnings
import textwrap

import dateparser
import regex
from muutils.json_serialize import json_serialize, SerializableDataclass, serializable_dataclass, serializable_field

def warn(message: str) -> None:
	# warnings.warn(message)
	print(message, file=sys.stderr)

MARKDOWN_OUTPUT_FORMAT: str = """ - [{done_chk}] {tag} **{title}**  
    {description}  
    *origin:* [[{origin_file_dendron}]] (line {origin_line})
    *time:* {time_str_out}  
"""
# ```py
# {data}
# ```

ICAL_TITLE_FMT: str = "[{tag_stripped}] {title}"

ICAL_DESCRIPTION_FMT: str = """{description}
origin: {origin_vscode_link}
time: {time_str_out} 
"""

def to_ascii(s: str) -> str:
	return s.encode('ascii',errors='ignore').decode()

def _markdown_output_process_path_dendron(s: str) -> str:
	"""only leave the filename, strip `.md` extension and directory"""
	return Path(s).stem
	

# only for sorting events -- events without date will always come after all other events
DISTANT_FUTURE_TIME: datetime = datetime(year=2030, month=1, day=1)

@serializable_dataclass(kw_only=True)
class Config(SerializableDataclass):
	"""configuration for the script. meant to be used as a global variable"""
	dendron_event_tags: tuple[str] = serializable_field(default=("#vtodo", "#vevent"))
	exclude_if_true: tuple[str] = serializable_field(default=("_done", "cancelled", "backlog")) # checks for these keys in `event.data`
	glob_regex_exclude: tuple[str] = serializable_field(default=tuple()) # exclude a file if it matches
	markdown_output_format: str = serializable_field(default=MARKDOWN_OUTPUT_FORMAT)
	ical_title_fmt: str = serializable_field(default=ICAL_TITLE_FMT)
	ical_description_fmt: str = serializable_field(default=ICAL_DESCRIPTION_FMT)
	description_delimiter: str = serializable_field(default='|')

	@classmethod
	def load(cls, data: dict) -> "Config":
		return cls(
			dendron_event_tags = tuple(set(data.get("dendron_event_tags", cls.dendron_event_tags))),
			exclude_if_true = tuple(set(data.get("exclude_if_true", cls.exclude_if_true))),
			glob_regex_exclude = tuple(set(data.get("glob_regex_exclude", cls.glob_regex_exclude))),
			markdown_output_format = data.get("markdown_output_format", cls.markdown_output_format),
			ical_title_fmt = data.get("ical_title_fmt", cls.ical_title_fmt),
			ical_description_fmt = data.get("ical_description_fmt", cls.ical_description_fmt),
			description_delimiter = data.get("description_delimiter", cls.description_delimiter),
		)

	@classmethod
	def load_file(cls, path: str) -> "Config":
		# print(f"reading config from: {path}", file = sys.stderr)
		with open(path, encoding="utf-8") as f:
			# text_raw: str = f.read()
			# print(text_raw, file=sys.stderr)
			data = json.load(f)
		return cls.load(data)

CFG: Config = Config()


GDRIVE_DOWNLOAD_FMT: str = "https://drive.google.com/uc?export=download&id={FILEID}"
GDRIVE_LINK_PREFIX: str = "https://drive.google.com/file/d/"

def process_gdrive_link(link: str) -> str:
	if link.startswith(GDRIVE_LINK_PREFIX):
		fileid = link[len(GDRIVE_LINK_PREFIX):].split("/")[0]
		return GDRIVE_DOWNLOAD_FMT.format(FILEID=fileid)


def parse_as_delta(s: str) -> timedelta:
	"""given a string like "30 min" return the appropriate timedelta
	
	uses `dateparser` package"""
	s = to_ascii(s)
	try:
		return datetime.now() - dateparser.parse(s)
	except regex._regex_core.error as e:
		warn(f"couldn't parse as delta: {s}")
		return timedelta(hours=1)

def custom_dateparse(s: str) -> date|datetime:
	"""Parse a date string using dateparser, with special handler for "today" """
	s = to_ascii(s)
	if s.lower() in {"today", "tod"}:
		return datetime.now().date()
	elif s.lower() in {"tomorrow", "tom", "tmro", "tmr"}:
		return datetime.now().date() + timedelta(days=1)
	else:
		dt: datetime 
		try:
			dt = dateparser.parse(s)
		except regex._regex_core.error as e:
			warn(f"regex._regex_core.error: couldn't parse: '{s}'\n{e}")
		except Exception as e:
			warn(f"unknown error: couldn't parse: '{s}'\n{e}")
		if dt is None:
			warn(f"got datetime as None for '{s}' in custom_dateparse, setting to datetime.now()")
			dt = datetime.now()
		if (dt.hour == 0 and dt.minute == 0 and dt.second == 0):
			# assume its just a date
			return dt.date()
		else:
			return dt

def round_timedelta_minutes(td: timedelta) -> str:
	"""round a timedelta to the nearest minute, and return as a string"""
	dt: timedelta = timedelta(minutes = round(td.total_seconds() / 60))
	return ":".join(str(dt).split(':')[:-1])

def date_to_datetime(d: date|datetime|None) -> datetime|None:
	if d is None:
		return None
	elif isinstance(d, datetime):
		return d
	elif isinstance(d, date):
		return datetime.combine(d, time())
	else:
		raise TypeError(f"Invalid type for to_datetime: {type(d) = } {d = }")


def bool_str_parse(s: str|int|bool, none_if_unknown: bool = False) -> bool|None:
	if isinstance(s, (int, bool)):
		return bool(s)
	elif isinstance(s, str):
		if s.lower() in {'true', '1', 'y', 'yes'}:
			return True
		elif s.lower() in {'false', '0', 'n', 'no'}:
			return False
		else:
			if none_if_unknown:
				return None
			else:
				raise ValueError(f"Invalid boolean string: {s}")
	else:
		raise TypeError(f"Invalid type for bool_str_parse: {type(s) = } {s = }")

def ical_datetime_format(dt: datetime|date) -> str:
	"""format as YYYYMMDDTHHMMSS for ical
	for example: 19970714T133000"""

	# need to be careful about the order of checks here because `datetime` is a subclass of `date`
	if isinstance(dt, datetime):
		return dt.strftime("%Y%m%dT%H%M%S")
	elif isinstance(dt, date):
		# see https://stackoverflow.com/questions/4330672/all-day-event-icalendar-gem
		# we return a dict which when serialized will produce something like
		# DTSTART;VALUE=DATE:20101117
		return dict(VALUE = f'DATE:{dt.strftime("%Y%m%d")}')
	else:
		raise TypeError(f"Invalid type for ical_datetime_format: {type(dt) = } {dt = }")

@serializable_dataclass(
	kw_only=True,
	properties_to_serialize=[
		"time_str_out",
		"done_chk",
		"origin_file",
		"origin_file_dendron",
		"origin_line",
		"origin_vscode_link",
		"tag_dendron",
		"tag_stripped",
		"time_start_readable",
		"duration_readable",
		"time_end_readable",
	],
)
class Event(SerializableDataclass):
	"""general event class"""
	time_start: datetime|date|None = serializable_field(
		serialization_fn = lambda d: d.isoformat() if d is not None else None,
		loading_fn = lambda d: custom_dateparse(d["time_start"]) if d.get("time_start", None) is not None else None,
	)
	duration: timedelta|None = serializable_field(
		serialization_fn = lambda d: d.total_seconds() if d is not None else None,
		loading_fn = lambda d: timedelta(seconds=d["duration"]) if d.get("duration", None) is not None else None,
	)
	title: str = serializable_field()
	description: str = serializable_field()
	tag: str|None = serializable_field(default=None)
	data: dict|None = serializable_field(default=None)
	allday: bool = serializable_field(default=False)
	done: bool = serializable_field(default=False)

	# derived properties
	@property
	def time_end(self) -> datetime:
		if self.duration is None:
			return self.time_start
		else:
			return self.time_start + self.duration

	@property
	def time_str_out(self) -> str:
		time_str: str
		if self.time_start is not None:
			if self.allday:
				time_str = self.time_start.strftime("%Y-%m-%d") + " (all day)"
			else:
				if self.time_start.date() == self.time_end.date():
					time_str = self.time_start.strftime("%Y-%m-%d %H:%M") + f" to " + self.time_end.strftime("%H:%M")
				else:
					time_str = self.time_start.strftime("%Y-%m-%d %H:%M") + f" to " + self.time_end.strftime("%Y-%m-%d %H:%M")
				time_str += f" (duration: {round_timedelta_minutes(self.duration)})"
		else:
			time_str = "(no time specified)"
		
		return time_str

	done_chk = property(lambda self: "x" if self.done else " ")
	origin_file = property(lambda self: Path(self.data["_file"]).as_posix())
	origin_file_dendron = property(lambda self: _markdown_output_process_path_dendron(self.data["_file"]))
	origin_line = property(lambda self: self.data["_line"])
	origin_vscode_link = property(lambda self: f"vscode://file/{Path(os.getcwd()) / self.origin_file}:{self.origin_line}")
	tag_dendron = property(lambda self: f"tags.{self.tag.lstrip('#')}" if self.tag is not None else None)
	tag_stripped = property(lambda self: ".".join(self.tag.split(".")[1:]) if self.tag is not None else None)

	time_start_readable = property(lambda self: date_to_datetime(self.time_start).isoformat() if self.time_start is not None else None)
	duration_readable = property(lambda self: str(self.duration) if self.duration is not None else None)
	time_end_readable = property(lambda self: date_to_datetime(self.time_end).isoformat() if self.time_end is not None else None)

	@classmethod
	def from_de_dict(cls, data: dict, default_duration: timedelta = parse_as_delta("30 min")) -> "Event":
		"""create an event from a dict of values created from a dendron note"""

		time_start: datetime|date|None
		duration: timedelta|None
		allday: bool = False
		
		# parse time
		# ========================================
		# only due time is specified
		if ("due" in data):
			time_start: datetime|date = custom_dateparse(data["due"])		
			if isinstance(time_start, datetime):
				# if exact time is specified, set to default duration
				allday = False
				duration = default_duration
			elif isinstance(time_start, date):
				# if only date is specified, set to all day
				# note that `datetime` is a subclass of `date`
				allday = True
				duration = None
			else:
				raise TypeError(f"Invalid type for time_start: {type(time_start) = } {time_start = }")


		# start and end time specified
		elif ("start" in data) and ("end" in data):
			time_start = custom_dateparse(data["start"])
			duration = custom_dateparse(data["end"]) - time_start

		# start time and duration specified
		elif ("start" in data) and ("duration" in data):
			time_start = custom_dateparse(data["start"])
			
			# parsing a duration such as "20 min" gives that length of time before the current time
			duration: timedelta = parse_as_delta(data["duration"])
		else:
			time_start = None
			duration = None

		# override allday if specified
		if ("allday" in data):
			allday = bool_str_parse(data["allday"])
		
		# format times according to allday
		if allday:
			if isinstance(time_start, datetime):
				time_start = time_start.date()

			if duration is not None:
				duration_days: timedelta = timedelta(days=duration.days)
				if duration_days != 0:
					duration = duration_days

		# parse completeness
		# ========================================
		done: bool = False
		if ("_done" in data):
			done = data["_done"]

		# parse title/description
		# ========================================
		# note: some of this logic happens in `find_dendron_events_from_file()` since we might have to grab multiple lines
		title: str; description: str
		if ("title" in data) and ("description" in data):
			# if both, set them
			title = data["title"]
			description = data["description"]
		elif ("title" in data) or ("description" in data):
			# if just one, something is wrong
			raise ValueError(f"Either both title and description must be specified, or neither. {data = }")
		elif CFG.description_delimiter in data["_content"]:
			# split it carefully in case there is more than one
			mid_idx: int = data["_content"].index(CFG.description_delimiter)
			title = data["_content"][:mid_idx]
			description = data["_content"][mid_idx+1:]
		else:
			# if neither, assume it's all the title
			title = data["_content"]
			description = "(no description)"


		title = title.strip()
		description = description.strip()

		# parse tag
		# ========================================
		tag: str|None
		if "_tag" in data:
			tag = data["_tag"]
		else:
			tag = None

		return cls(
			time_start = time_start,
			duration = duration,
			title = title,
			description = description,
			tag = tag,
			allday = allday,
			done = done,
			data = data,
		)

	def get_uid(self) -> str:
		return f"{Path(self.data['_file']).as_posix()}:{self.data['_line']}"

	def to_ical_dict(self) -> dict:
		"""serialize to ical-compatible dict"""
		today_date_str: str = ical_datetime_format(datetime.now().date())
		return {
			"UID" : self.get_uid(),
			"DTSTAMP" : ical_datetime_format(datetime.now()),
			"LAST-MODIFIED" : ical_datetime_format(datetime.now()),
			"DTSTART" : ical_datetime_format(self.time_start) if self.time_start is not None else today_date_str,
			"DTEND" : ical_datetime_format(self.time_end) if self.time_start is not None else today_date_str,
			# "CREATED" : ical_datetime_format(datetime.now()),
			# "LAST_MODIFIED" : ical_datetime_format(datetime.now()),
			"SUMMARY" : CFG.ical_title_fmt.format(**self.serialize()),
			"DESCRIPTION" : CFG.ical_description_fmt.format(**self.serialize()),
			"SEQUENCE" : 0,
			"TRANSP" : "OPAQUE",
			"STATUS" : "CONFIRMED",
		}

	def to_md_str(self) -> str:
		"""serialize for writing to markdown log file"""
		return CFG.markdown_output_format.format(**self.serialize())


def _time_start_loader(data: dict) -> datetime|date:
	timestamp: float|None = data["time_start"]
	if timestamp is None:
		return None
	else:
		dt: datetime = datetime.fromtimestamp(timestamp)
		# if it's an all-day event, return a date
		if data["allday"]:
			return dt.date()
		else:
			return dt



DENDRON_EVENT_REGEX: re.Pattern = re.compile(
	r"^(?P<before>.*?)(?P<chk_done>\[[ x]\])?\s*(?P<tag>\#\w+(\.\w+)*)\s*(?P<metadata>\{.*\})?\s*(?P<content>.*)$"
)  # thx copilot :)
"""
`--- [x] #todo.subtag {.c1 .c2 k1=v1 k2=v2} content`
will map to
before = "--- "
chk_done = "[x]"
tag = "#todo.subtag"
metadata = ".class .class key=value key=value" 
content = "content"

note:
 - metadata is optional, but always in brackets if present
 - tags should be allowed to have dots in them "."
 - `before` can be any text
 - `chk_done` is optional
"""

def parse_dendron_event(event: str) -> dict|None:
	"""
	```
	#todo {.class .class key=value key=value} content
	```

	### Parameters:
	 - `event : str`   
	
	### Returns:
	`dict`	
	- `_tag` will be the tag
	- `_content` will be the content
	classes present will map to True in the dict of key/value pairs
	"""	

	# use a regex to separate the stuff in brackets
	tag: str|None; metadata: str|None; content: str|None; chk_done: str|None
	match: re.Match = DENDRON_EVENT_REGEX.match(event)
	if match:
		tag = match.group("tag")
		metadata = match.group("metadata")
		content = match.group("content")
		chk_done = match.group("chk_done")

		if metadata is None:
			metadata = ""
		else:
			metadata = metadata[1:-1] # strip curly braces

		if content is None:
			content = ""
				
	else:
		return None

	# parse the metadata
	classes: set[str] = set()
	kvmap: dict = {}

	# put metadata into list
	metadata_list: list[str] = list()
	for item in metadata.split():
		if item.startswith("."):
			metadata_list.append(item)
		elif "=" in item:
			metadata_list.append(item)
		else:
			# check if theres an unbalanced quote
			if metadata_list[-1].count('"') % 2 == 1:
				metadata_list[-1] += " " + item
			else:
				raise ValueError(f"invalid metadata: {item = } in {metadata = }")

	# put into dict
	for item in metadata_list:
		if item.startswith("."):
			classes.add(item[1:])
		elif "=" in item:
			k, v = item.split("=")
			kvmap[k] = v.strip('"')
		else:
			raise ValueError(f"Invalid metadata item: {item}")

	# check doneness (metadata takes priority)
	evnt_done: bool = False
	time_done: datetime|None = None
	if "done" in kvmap:
		parsing_done: bool|None = bool_str_parse(kvmap["done"], none_if_unknown=True)
		if isinstance(parsing_done, bool):
			evnt_done = parsing_done
		else:
			# assume it's a date, if its not a bool
			evnt_done = True
			time_done = custom_dateparse(kvmap["done"])

	elif "done" in classes:
		evnt_done = True
	elif chk_done is not None:
		evnt_done = ("[x]" in chk_done)

	# combine and return
	return {
		"_tag": tag,
		"_content": content,
		"_done": evnt_done,
		"_time_done": time_done,
		**kvmap,
		**{c: True for c in classes},
		"_raw": event,
	}

def find_dendron_events_from_file(
		filename: str,
		allow_tag_mid_line: bool = False,
	) -> list[dict]:
	"""reads a dendron-markdown file, gets all events from it"""

	if allow_tag_mid_line:
		raise NotImplementedError("allow_tag_mid_line not implemented")

	output: list[dict] = list()
	with open(filename, "r", encoding="utf-8") as f:
		# iterate over *array* with all lines, since we might need to grab the lines
		data: list[str] = list(f.readlines())
		for linenum, line in enumerate(data):
			# check for any valid tags
			if any((tag in line) for tag in CFG.dendron_event_tags):
				try:
					event: dict|None = parse_dendron_event(line)
				except ValueError as e:
					warnings.warn(f"Error parsing {filename}:{linenum + 1}\n{e}")
					event = None
				if event is not None:
					# get info about file location
					event["_file"] = filename
					event["_line"] = linenum + 1

					# if ends with CFG.description_delimiter, them get all lines until the next empty line
					if line.rstrip().endswith(CFG.description_delimiter):
						event["title"] = event["_content"].rstrip().rstrip(CFG.description_delimiter).rstrip()
						desc_lines: list[str] = list()
						for i in range(linenum + 1, len(data)):
							if data[i].strip() == "":
								break
							desc_lines.append(data[i])

						if len(desc_lines) > 0:
							# find and strip any *common* leading whitespace/indentation using textwrap.dedent
							desc_lines = textwrap.dedent("".join(desc_lines)).splitlines()
							# format and store to a string in the dict
							# NOTE: this is fragile -- if you change the markdown format, it might not look quite right
							event["description"] = "".join([
								f"\n    {dl}  "
								for dl in desc_lines
							])

					output.append(event)

	return output

def glob_get_dendron_events(
		glob_pattern: str,
	) -> list[dict]:

	regexes_exclude: list[re.Pattern] = [re.compile(pattern) for pattern in CFG.glob_regex_exclude]

	output: list[dict] = list()
	for filename in glob.glob(glob_pattern):
		if not any((regex.match(filename) for regex in regexes_exclude)):
			# print(f"reading: {filename}", file = sys.stderr)
			try:
				output.extend(find_dendron_events_from_file(filename))
			except (UnicodeDecodeError, UnicodeError, FileNotFoundError, ValueError) as e:
				warn(f"Error reading {filename}: {e}")

	return output


def ical_process_value(s: str|int|float) -> str:
	"""
	Process a string to be safe for icalendar

	from https://datatracker.ietf.org/doc/html/rfc5545, pg 45:

	```
	ESCAPED-CHAR = ("\\" / "\;" / "\," / "\n")
          ; \\ encodes \, \n encodes newline
          ; \; encodes ;, \, encodes ,
	```

	note: we never emit newlines with capital N because this causes problems for python. 
	"""
	if isinstance(s, (int, float)):
		return str(s)
	elif isinstance(s, str):
		return (
			s
			.replace("\\", "\\\\")
			.replace("\n", "\\n")
			.replace(";", "\\;")
			.replace(",", "\\,")
		)
	else:
		raise TypeError(f"invalid type: {type(s) = } {s = }")


def ical_serialize_dict(d: dict, bounder: str|None = None) -> str:
	"""
	Serialize a dict to a string that can be used in an icalendar event
	"""
	output: list[str] = list()
	for k, v in d.items():
		if isinstance(v, (str, int, float)):
			output.append(f"{k}:{ical_process_value(v)}")
		elif isinstance(v, dict):
			joined_dict_items: str = ';'.join([f'{k2}={ical_process_value(v2)}' for k2, v2 in v.items()])
			output.append(f"{k};{joined_dict_items}")
		else:
			raise ValueError(f"Unknown type {type(v) = } {k = } {v = }")

	if bounder is not None:
		output = [
			f"BEGIN:{bounder}",
			*output,
			f"END:{bounder}",
		]

	return "\n".join(output)


def create_ical_content(events: list[Event], dateless_events_today: bool = True) -> str:
	HEADER: str = """BEGIN:VCALENDAR"""
	FOOTER: str = """END:VCALENDAR"""
	
	HEADER_META: dict[str,str] = dict(
		VERSION=2.0,
		PRODID="-//bobbin v0.1//NONSGML Dendron//EN",
		CALSCALE="GREGORIAN",
		METHOD="PUBLISH",
	)

	output: str = "\n".join([
		HEADER,
		ical_serialize_dict(HEADER_META),
		*[
			ical_serialize_dict(event.to_ical_dict(), bounder="VEVENT")
			for event in events
			if event.time_start is not None or dateless_events_today
		],
		FOOTER,
	])

	return output


def create_md_content(events: list[Event]) -> str:
	HEADER: str = """# Events"""

	# group events by tag
	tags_found: set[str] = set(e.tag for e in events)

	tag_grouped: dict[str, list[Event]] = {
		tag: [e for e in events if e.tag == tag]
		for tag in tags_found
	}

	# sort the events by time
	tag_grouped_sorted: dict[str, list[Event]] = dict()
	for tag, e_list in tag_grouped.items():
		tag_grouped_sorted[tag] = sorted(e_list, key=lambda e: date_to_datetime(e.time_start) if e.time_start is not None else DISTANT_FUTURE_TIME)

	# create the output
	output: str = "\n".join([
		HEADER,
		*[
			f"## {tag.lstrip('#')}\n" + "\n".join([ e.to_md_str() for e in e_list ])
			for tag, e_list in tag_grouped.items()
		],
	])

	return output


def load_events_json(filename: str) -> list[Event]:
	"""loads as json or jsonl depending on file extension"""

	if filename.endswith(".json"):
		with open(filename, "r", encoding="utf-8") as f:
			return [Event.load(d) for d in json.load(f)]

	elif filename.endswith(".jsonl"):
		output: list[Event] = list()
		with open(filename, "r", encoding="utf-8") as f:
			for line in f:
				output.append(Event.load(json.loads(line)))
		return output


def filter_events(events: list[Event], cfg: Config = CFG) -> list[Event]:
	"""filters events according to the config"""
	return [
		e for e in events
		if not any(
			bool_str_parse(e.data.get(x, False))
			for x in cfg.exclude_if_true
		)
	]


def general_loader(path: str, cfg_path: str|None = None) -> list[Event]:
	"""given a path, determine whether it is a glob of markdown 
	files or a processed json/jsonl file, and load
	
	also, load config from the specified file if given
	"""
	global CFG # pylint: disable=global-statement

	if cfg_path is not None:
		CFG = Config.load_file(cfg_path)

	if path.endswith(".json") or path.endswith(".jsonl"):
		return filter_events(load_events_json(path))
	else:
		data_raw: list[dict] = glob_get_dendron_events(path)
		return filter_events([Event.from_de_dict(e) for e in data_raw])
	

def events_to_json(data_events: list[Event], jsonl: bool = False) -> str:
	"""
	Convert dendron events to json format, print to console
	"""
	data_json: list[dict] = [d.serialize() for d in data_events]
	
	if jsonl:
		return "\n".join([json.dumps(d) for d in data_json])
	else:
		return json.dumps(data_json, indent="\t")

if __name__ == "__main__":

	if any(
			arg.lower().lstrip("-") in {"help", "h"} 
			for arg in sys.argv
		):
		print(__doc__)
		sys.exit(0)

	# print(sys.argv, file = sys.stderr)

	import fire
	fire.Fire({
		"json": lambda path, cfg_path=None : events_to_json(general_loader(path, cfg_path)),
		"jsonl": lambda path, cfg_path=None : events_to_json(general_loader(path, cfg_path), jsonl=True),
		"ical": lambda path, cfg_path=None : create_ical_content(general_loader(path, cfg_path)),
		"md": lambda path, cfg_path=None : create_md_content(general_loader(path, cfg_path)),
		"markdown": lambda path, cfg_path=None : create_md_content(general_loader(path, cfg_path)),
		"process_gdrive_link" : process_gdrive_link,
	})



