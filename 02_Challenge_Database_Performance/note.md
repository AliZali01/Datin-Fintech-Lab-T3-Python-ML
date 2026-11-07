## Access other project to this project
python -m pip install -e ..\01_Challenge_Data_Factory

## import project 1
python -c "import data_factory; print(data_factory.__file__)"

## check all test
python -m unittest discover -s tests -v