import argparse
import json
from pathlib import Path

import yaml
from jsonschema.validators import validator_for


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Validate Render Blueprint YAML files against a local JSON Schema.'
    )
    parser.add_argument('--schema', type=Path, required=True)
    parser.add_argument('blueprints', nargs='+', type=Path)
    options = parser.parse_args()

    schema = json.loads(options.schema.read_text(encoding='utf-8'))
    validator_class = validator_for(schema)
    validator_class.check_schema(schema)
    validator = validator_class(schema)
    failed = False
    for blueprint_path in options.blueprints:
        blueprint = yaml.safe_load(blueprint_path.read_text(encoding='utf-8'))
        errors = sorted(
            validator.iter_errors(blueprint),
            key=lambda error: [str(part) for part in error.absolute_path],
        )
        if not errors:
            print(f'{blueprint_path}: valid')
            continue
        failed = True
        print(f'{blueprint_path}: invalid')
        for error in errors:
            location = '/'.join(str(part) for part in error.absolute_path) or '<root>'
            print(f'  {location}: {error.message}')
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
