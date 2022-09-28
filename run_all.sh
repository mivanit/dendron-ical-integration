RUN_SCRIPT="py make_cal.py"
SOURCE_GLOB="test/source/*.md"
CONFIG_PATH="test/cfg.json"
OUTPUT_DIR="test/output"

# jsonl/jsonl from source
$RUN_SCRIPT json $SOURCE_GLOB $CONFIG_PATH > $OUTPUT_DIR/cal.json
$RUN_SCRIPT jsonl $SOURCE_GLOB $CONFIG_PATH > $OUTPUT_DIR/cal.jsonl

# ics + md from source
$RUN_SCRIPT ical $SOURCE_GLOB $CONFIG_PATH > $OUTPUT_DIR/cal.ics
$RUN_SCRIPT md $SOURCE_GLOB $CONFIG_PATH > $OUTPUT_DIR/cal.md

# # all from json
# $RUN_SCRIPT json $OUTPUT_DIR/cal.json > $OUTPUT_DIR/cal_from-json.json
# $RUN_SCRIPT jsonl $OUTPUT_DIR/cal.json > $OUTPUT_DIR/cal_from-json.jsonl
# $RUN_SCRIPT ical $OUTPUT_DIR/cal.json > $OUTPUT_DIR/cal_from-json.ics
# $RUN_SCRIPT md $OUTPUT_DIR/cal.json > $OUTPUT_DIR/cal_from-json.md

# # all from jsonl
# $RUN_SCRIPT json $OUTPUT_DIR/cal.jsonl > $OUTPUT_DIR/cal_from-jsonl.json
# $RUN_SCRIPT jsonl $OUTPUT_DIR/cal.jsonl > $OUTPUT_DIR/cal_from-jsonl.jsonl
# $RUN_SCRIPT ical $OUTPUT_DIR/cal.jsonl > $OUTPUT_DIR/cal_from-jsonl.ics
# $RUN_SCRIPT md $OUTPUT_DIR/cal.jsonl > $OUTPUT_DIR/cal_from-jsonl.md

