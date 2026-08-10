.PHONY: check

check:
	python3 -m py_compile nemo_action_bar.py tests/validate_config.py
	PYTHONPATH=. python3 tests/validate_config.py
	python3 -m json.tool buttons.json >/dev/null
	shellcheck install.sh uninstall.sh
