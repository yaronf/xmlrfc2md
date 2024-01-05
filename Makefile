.PHONY: build upload clean

build:
	python3.10 -m pip install --upgrade build
	python3.10 -m build

upload:
	twine upload dist/*

clean:
	rm -rf dist
	rm -rf build
	rm -rf *.egg-info
