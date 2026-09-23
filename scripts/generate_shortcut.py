#!/usr/bin/env python3
"""Generate an unsigned shortcut from source; scripts/apply.sh signs it with Apple."""
import argparse
from pathlib import Path
import plistlib
import uuid

SCRIPT = '''if [ "$#" -ne 1 ]; then
  echo "Select exactly one EPUB in Finder, then run Book to Kindle." >&2
  exit 1
fi
app="$HOME/Applications/Book to Kindle.app"
if [ ! -d "$app" ]; then
  echo "Book to Kindle is not installed. Run install.command first." >&2
  exit 1
fi
/usr/bin/open -n "$app" --args --file "$1"
'''


def workflow():
    return {
        'WFWorkflowClientVersion': '2600.0.3',
        'WFWorkflowMinimumClientVersion': 900,
        'WFWorkflowMinimumClientVersionString': '900',
        'WFWorkflowIcon': {'WFWorkflowIconStartColor': 4271458815, 'WFWorkflowIconGlyphNumber': 61440},
        'WFWorkflowTypes': ['QuickActions'],
        'WFQuickActionSurfaces': ['Finder', 'Services'],
        'WFWorkflowInputContentItemClasses': ['WFGenericFileContentItem'],
        'WFWorkflowOutputContentItemClasses': [],
        'WFWorkflowHasOutputFallback': False,
        'WFWorkflowHasShortcutInputVariables': True,
        'WFWorkflowImportQuestions': [],
        'WFWorkflowNoInputBehavior': {'Name': 'WFWorkflowNoInputBehaviorAskForInput', 'Parameters': {'ItemClass': 'WFGenericFileContentItem'}},
        'WFWorkflowActions': [{
            'WFWorkflowActionIdentifier': 'is.workflow.actions.runshellscript',
            'WFWorkflowActionParameters': {
                'UUID': str(uuid.UUID('608395c2-e99f-4e32-a460-4be217b272e4')).upper(),
                'Script': SCRIPT,
                'Shell': '/bin/zsh',
                'InputMode': 'as arguments',
                'Input': {'WFSerializationType': 'WFTextTokenAttachment', 'Value': {
                    'Type': 'ExtensionInput',
                    'Aggrandizements': [{'Type': 'WFPropertyVariableAggrandizement', 'PropertyName': 'File Path'}],
                }},
            },
        }],
    }

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(plistlib.dumps(workflow(), fmt=plistlib.FMT_XML, sort_keys=True))
