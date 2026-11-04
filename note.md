## path python
python -c "import sys; print(sys.executable)"

## Check ignore "datafactory-env/" by .gitignore file
git check-ignore -v datafactory-env/

## show files Change
git diff --cached

## package
New-Item -ItemType File -Force -Path `
    "src\data_factory\__init__.py", `
    "tests\__init__.py", `
    "data\curated\.gitkeep"

## Check Spacing files
git diff --cached --check

## Change Summerize
git diff --cached --stat

## Create & Switch Branch
git switch -c feature/http-client

##  کتابخانه‌ای برای محاسبات هندسی و تشخیص قرارگرفتن یک نقطه در محدوده یک چندضلعی است
pip install shapely

## test
python -m pytest .\tests -v --tb=short