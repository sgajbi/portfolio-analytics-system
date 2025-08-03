# libs/portfolio-common/tests/conftest.py

# This line explicitly tells pytest to load all fixtures from the root conftest.py file.
# This makes the shared fixtures (like docker_services, db_engine, clean_db)
# available to all tests within this directory and its subdirectories.
pytest_plugins = "tests.conftest"