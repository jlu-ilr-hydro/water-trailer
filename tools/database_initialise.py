from trailer.db.engine import engine, metadata

# Initialise the tables in the database (only needs to be run once or if new tables are added to the database)
metadata.create_all(engine)