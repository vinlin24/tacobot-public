VENV = $(PWD)/.venv
PACKAGE = bot

ifeq ($(OS),Windows_NT)
	PYTHON=$(VENV)/Scripts/python.exe
else
	PYTHON=$(VENV)/bin/python
endif

# TODO: Turn code into a package and run the package.
.PHONY: default
default:
	@cd src && $(PYTHON) -m $(PACKAGE)

.PHONY: clean
clean:
	-find . -maxdepth 1 -type d -name __pycache__ -exec rm -rf {} +
	-find src -type d -name __pycache__ -o -name "*.egg-info" \
		-exec rm -rf {} +
