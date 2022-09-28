"""scrape dendron events from a vault, outputs them to ical, markdown, json, jsonl



ical file format spec: https://datatracker.ietf.org/doc/html/rfc5545
"""

from dataclasses import dataclass, asdict
from functools import partial
import json
import sys
from typing import Callable, Literal
from datetime import datetime, timedelta, date, time
import re
import glob

import dateparser
from muutils.json_serialize import json_serialize, dataclass_loader_factory, dataclass_serializer_factory

GDRIVE_DOWNLOAD_FMT: str = "https://drive.google.com/uc?export=download&id={FILEID}"
GDRIVE_LINK_PREFIX: str = "https://drive.google.com/file/d/"


MARKDOWN_OUTPUT_FORMAT: str = """ - [{done_chk}] [[{tag}._log]] **{title}**  
    {description}  
    *origin:* [[{origin_file}]] (line {origin_line})  {time_str}  
    ```py
    {data}
    ```
"""

@dataclass
class Config:
	DENDRON_EVENT_TAGS: tuple[str] = ("#vtodo", "#vevent")
	MARKDOWN_OUTPUT_FORMAT: str = MARKDOWN_OUTPUT_FORMAT

	@classmethod
	def load(cls, data: dict) -> "Config":
		return cls(
			DENDRON_EVENT_TAGS = tuple(set(data.get("DENDRON_EVENT_TAGS", cls.DENDRON_EVENT_TAGS))),
			MARKDOWN_OUTPUT_FORMAT = data.get("MARKDOWN_OUTPUT_FORMAT", cls.MARKDOWN_OUTPUT_FORMAT),
		)

	@classmethod
	def load_file(cls, path: str) -> "Config":
		with open(path) as f:
			data = json.load(f)
		return cls.load(data)

CFG: Config = Config()


def process_gdrive_link(link: str) -> str:
	if link.startswith(GDRIVE_LINK_PREFIX):
		fileid = link[len(GDRIVE_LINK_PREFIX):].split("/")[0]
		return GDRIVE_DOWNLOAD_FMT.format(FILEID=fileid)


def parse_as_delta(s: str) -> timedelta:
	return datetime.now() - dateparser.parse(s)

def custom_dateparse(s: str) -> date|datetime:
	"""Parse a date string using dateparser, with special handler for "today" """
	if s.lower() in {"today", "tod"}:
		return datetime.now().date()
	elif s.lower() in {"tomorrow", "tom", "tmro", "tmr"}:
		return datetime.now().date() + timedelta(days=1)
	else:
		dt: datetime = dateparser.parse(s)
		if (dt.hour == 0 and dt.minute == 0 and dt.second == 0):
			# assume its just a date
			return dt.date()
		else:
			return dt

def round_timedelta_minutes(td: timedelta) -> str:
	"""round a timedelta to the nearest minute, and return as a string"""
	dt: timedelta = timedelta(minutes = round(td.total_seconds() / 60))
	return ":".join(str(dt).split(':')[:-1])

def date_to_datetime(d: date|datetime) -> datetime:
	if isinstance(d, datetime):
		return d
	elif isinstance(d, date):
		return datetime.combine(d, time())
	else:
		raise TypeError(f"Invalid type for to_datetime: {type(d) = } {d = }")


def bool_str_parse(s: str|int|bool) -> bool:
	if isinstance(s, (int, bool)):
		return bool(s)
	elif isinstance(s, str):
		if s.lower() in {'true', '1', 'y', 'yes'}:
			return True
		elif s.lower() in {'false', '0', 'n', 'no'}:
			return False
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

@dataclass(kw_only=True)
class Event:
	"""general event class"""
	time_start: datetime|date|None
	duration: timedelta|None
	title: str
	description: str
	tag: str|None = None
	data: dict|None = None
	allday: bool = False
	done: bool = False

	@property
	def time_end(self) -> datetime:
		if self.duration is None:
			return self.time_start
		else:
			return self.time_start + self.duration

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
				duration_days: int = timedelta(days=duration.days)
				if duration_days != 0:
					duration = duration_days

		# parse completeness
		# ========================================
		done: bool = False
		if ("_done" in data):
			done = data["_done"]

		# parse title/description
		# ========================================
		title: str; description: str
		if "title" in data:
			title = data["title"]
			description = data["_desc"]
		elif '|' in data["_desc"]:
			# split it carefully in case there is more than one
			mid_idx: int = data["_desc"].index('|')
			title = data["_desc"][:mid_idx]
			description = data["_desc"][mid_idx+1:]
		else:
			title = data["_desc"]
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
		return f"{self.data['_file']}:{self.data['_line']}"

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
			"SUMMARY" : self.title,
			"DESCRIPTION" : self.description,
			"SEQUENCE" : 0,
			"TRANSP" : "OPAQUE",
			"STATUS" : "CONFIRMED",
		}

	def to_md_str(self) -> str:
		"""serialize for writing to markdown log file"""
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
			time_str = f"\n    *time:* " + time_str + "  \n"
		else:
			time_str = ""

		return CFG.MARKDOWN_OUTPUT_FORMAT.format(
			done_chk = "x" if self.done else " ",
			tag = self.tag,
			title = self.title,
			description = self.description,
			origin_file = self.data["_file"],
			origin_line = self.data["_line"],
			time_str = time_str,
			data = self.data,
		)

Event.serialize = dataclass_serializer_factory(
	Event,
	{
		"time_start" : lambda self: date_to_datetime(self.time_start).timestamp() if self.time_start is not None else None,
		"time_start_readable" : lambda self: date_to_datetime(self.time_start).isoformat() if self.time_start is not None else None,
		"duration" : lambda self: self.duration.total_seconds() if self.duration is not None else None,
		"duration_readable" : lambda self: str(self.duration) if self.duration is not None else None,
		"time_end" : lambda self: date_to_datetime(self.time_end).timestamp() if self.time_end is not None else None,
		"time_end_readable" : lambda self: date_to_datetime(self.time_end).isoformat() if self.time_end is not None else None,
	},
) 

Event.load = dataclass_loader_factory(
	Event,
	{
		"time_start" : lambda data: datetime.fromtimestamp(data["time_start"]) if data["time_start"] is not None else None,
		"duration" : lambda data: timedelta(seconds=data["duration"]) if data["duration"] is not None else None,
	},
	# TODO: some validation?
)

DENDRON_EVENT_REGEX: re.Pattern = re.compile(r"^(?P<before>.*?)(?P<chk_done>\[[ x]\])?\s*(?P<tag>\#\w+(\.\w+)*)\s*(?P<metadata>\{.*\})?\s*(?P<description>.*)$")  # thx copilot :)
"""
`--- [x] #todo.subtag {.c1 .c2 k1=v1 k2=v2} description`
will map to
before = "--- "
chk_done = "[x]"
tag = "#todo.subtag"
metadata = ".class .class key=value key=value" 
description = "description"

note:
 - metadata is optional, but always in brackets if present
 - tags should be allowed to have dots in them "."
 - `before` can be any text
 - `chk_done` is optional
"""

def parse_dendron_event(event: str) -> dict|None:
	"""
	```
	#todo {.class .class key=value key=value} description
	```

	### Parameters:
	 - `event : str`   
	
	### Returns:
	`dict`	
	- `_tag` will be the tag
	- `_desc` will be the description
	classes present will map to True
	"""	

	# use a regex to separate the stuff in brackets
	tag: str|None; metadata: str|None; description: str|None; chk_done: str|None
	match: re.Match = DENDRON_EVENT_REGEX.match(event)
	if match:
		tag = match.group("tag")
		metadata = match.group("metadata")
		description = match.group("description")
		chk_done = match.group("chk_done")

		if metadata is None:
			metadata = ""
		else:
			metadata = metadata[1:-1] # strip curly braces

		if description is None:
			description = ""
				
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
	if "done" in kvmap:
		evnt_done = bool_str_parse(kvmap["done"])
	elif chk_done is not None:
		evnt_done = (chk_done == "[x]")

	# combine and return
	return {
		"_tag": tag,
		"_desc": description,
		"_done": evnt_done,
		**kvmap,
		**{c: True for c in classes},
		"_raw": event,
	}

def find_dendron_events_from_file(
		filename: str,
		allow_tag_mid_line: bool = False,
		descripton_append_until_emptyline: bool = False,
	) -> list[dict]:

	if allow_tag_mid_line:
		raise NotImplementedError("allow_tag_mid_line not implemented")

	if descripton_append_until_emptyline:
		raise NotImplementedError("descripton_append_until_emptyline not implemented")

	output: list[dict] = list()
	with open(filename, "r", encoding="utf-8") as f:
		for linnum, line in enumerate(f):
			if any((tag in line) for tag in CFG.DENDRON_EVENT_TAGS):
				todo_idx_start: int = line.find("#todo")
				event: dict|None = parse_dendron_event(line[todo_idx_start:])
				if event is not None:
					event["_file"] = filename
					event["_line"] = linnum + 1
					output.append(event)

	return output

def glob_get_dendron_events(
		glob_pattern: str,
	) -> list[dict]:

	output: list[dict] = list()
	for filename in glob.glob(glob_pattern):
		print(f"reading: {filename}", file = sys.stderr)
		try:
			output.extend(find_dendron_events_from_file(filename))
		except (UnicodeDecodeError, UnicodeError, FileNotFoundError, ValueError) as e:
			print(f"Error reading {filename}: {e}")

	return output



def ical_serialize_dict(d: dict, bounder: str|None = None) -> str:
	"""
	Serialize a dict to a string that can be used in an icalendar event
	"""
	output: list[str] = list()
	for k, v in d.items():
		if isinstance(v, (str, int, float)):
			output.append(f"{k}:{v}")
		elif isinstance(v, dict):
			joined_dict_items: str = ';'.join([f'{k2}={v2}' for k2, v2 in v.items()])
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
		tag_grouped_sorted[tag] = sorted(e_list, key=lambda e: date_to_datetime(e.time_start))

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


def general_loader(path: str, cfg_path: str|None = None) -> list[Event]:
	"""given a path, determine whether it is a glob of markdown 
	files or a processed json/jsonl file, and load
	
	also, load config from the specified file if given
	"""
	global CFG # pylint: ignore

	if cfg_path is not None:
		CFG = Config.load_file(cfg_path)
	

	if path.endswith(".json") or path.endswith(".jsonl"):
		return load_events_json(path)
	else:
		data_raw: list[dict] = glob_get_dendron_events(path)
		return [Event.from_de_dict(e) for e in data_raw]
	

def events_to_json(data_events: list[Event], jsonl: bool = False) -> str:
	"""
	Convert dendron events to json format, print to console
	"""
	data_json: list[dict] = json_serialize(data_events)
	
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

	import fire
	fire.Fire({
		"json": lambda path, cfg_path=None : events_to_json(general_loader(path, cfg_path)),
		"jsonl": lambda path, cfg_path=None : events_to_json(general_loader(path, cfg_path), jsonl=True),
		"ical": lambda path, cfg_path=None : create_ical_content(general_loader(path, cfg_path)),
		"md": lambda path, cfg_path=None : create_md_content(general_loader(path, cfg_path)),
		"markdown": lambda path, cfg_path=None : create_md_content(general_loader(path, cfg_path)),
	})




