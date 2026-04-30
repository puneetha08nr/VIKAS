 sudo -u postgres psql                                                                                                                    
                                                                                                                                           
  Then inside psql, run these commands:                                                                                                    
                                                                                                                                           
  -- Create the user if it doesn't exist (skip if it does)                                                                                 
  CREATE USER vikas WITH PASSWORD 'vikas_dev';                                                                                             
   
  -- Or if the user already exists, just reset the password:                                                                               
  ALTER USER vikas WITH PASSWORD 'vikas_dev';                                                                                            
                                                                                                                                           
  -- Create the database if it doesn't exist                                                                                             
  CREATE DATABASE vikas OWNER vikas;

  -- Grant privileges                                                                                                                      
  GRANT ALL PRIVILEGES ON DATABASE vikas TO vikas;
                                                                                                                                           
  \q                                                                                                                                     

  Then verify the connection works:                                                                                                        
   
  psql "postgresql://vikas:vikas_dev@localhost:5432/vikas" -c "SELECT 1"                                                                   
  \q

  Then verify the connection works:

  psql "postgresql://vikas:vikas_dev@localhost:5432/vikas" -c "SELECT 1"

  ---
  If you can't use sudo, you can also try connecting as your system user if you have a matching PostgreSQL role:

  psql -d postgres -c "ALTER USER vikas WITH PASSWORD 'vikas_dev';"

  Once the connection works, you'll be able to run Alembic migrations normally. Let me know what you see after running those commands.

You have two PostgreSQL clusters: PG13 on port 5432 (where vikas DB lives) and PG17 on port 5433. The project requires PG16+, so I'd     
  recommend moving to PG17 rather than staying on PG13.                                                                                    
                                                                                                                                           
  Option A — Stay on PG13 (quick fix, not ideal):                                                                                          
  sudo apt install postgresql-13-pgvector                                                                                                  
                                                                                                                                           
  Option B — Move to PG17 (recommended — matches project spec):                                                                            
                                                                                                                                           
  Run these commands:                                                                                                                      
                  
  # Install pgvector for PG17
  sudo apt install postgresql-17-pgvector                                                                                                  
   
  # Create vikas user + DB on PG17 (port 5433)                                                                                             
  sudo -u postgres psql -p 5433 -c "CREATE USER vikas WITH PASSWORD 'vikas_dev';"
  sudo -u postgres psql -p 5433 -c "CREATE DATABASE vikas OWNER vikas;"                                                                    
  sudo -u postgres psql -p 5433 -c "GRANT ALL PRIVILEGES ON DATABASE vikas TO vikas;"
                                                                                                                                           
  Then update your .env to point to port 5433:

  DATABASE_URL=postgresql+asyncpg://vikas:vikas_dev@localhost:5433/vikas
                                                                                                                                           
  Verify it works:
  psql "postgresql://vikas:vikas_dev@localhost:5433/vikas" -c "CREATE EXTENSION IF NOT EXISTS vector; SELECT extversion FROM pg_extension  
  WHERE extname='vector';"                                                                                                                
                                                                                                                                           
  After that, re-run your Alembic migrations and everything should work. Which option do you want to go with?
                                                                                                                                           
✻ Churned for 18s 
                                                                                                                                           
※ recap: Setting up the Vikas project database. The vikas user password was fixed and pgvector is missing. Next: run `sudo apt install     
  postgresql-17-pgvector` then recreate the vikas user on port 5433. (disable recaps in /config)
                                                                                                                                           
❯ (base) puneetha@puneetha-Latitude-7410:~/Documents/IterativeResearch/VIKAS/apps/api$ sudo  psql                                          
  "postgresql://vikas:vikas_dev@localhost:5433/vikas" -c "CREATE EXTENSION IF NOT EXISTS vector; SELECT extversion FROM pg_extension       
    WHERE extname='vector';"                                                                                                               
  ERROR:  permission denied to create extension "vector"                                                                                   
  HINT:  Must be superuser to create this extension.                                                                                       

● The vector extension must be created by a superuser. Run it as postgres:
                                                                                                                                       
  sudo -u postgres psql -p 5433 -d vikas -c "CREATE EXTENSION IF NOT EXISTS vector;"
                                                                                                                                           
  Then verify:
  psql "postgresql://vikas:vikas_dev@localhost:5433/vikas" -c "SELECT extversion FROM pg_extension WHERE extname='vector';"                
                                                                                                                           
  After that, your Alembic migration should pass the CREATE EXTENSION IF NOT EXISTS vector step cleanly since the extension will already   
  exist.                                                                                                                                   
                                                                                                                                           
✻ Churned for 3s                                                                                                                           
                                                                                                                                       
❯  File "/home/puneetha/Documents/IterativeResearch/VIKAS/.venv/lib/python3.12/site-packages/sqlalchemy/dialects/postgresql/asyncpg.py",   
  line 797, in _handle_exception                                                                                                           
      raise translated_error from error                                                                                                    
  sqlalchemy.exc.ProgrammingError: (sqlalchemy.dialects.postgresql.asyncpg.ProgrammingError) <class                                        
  'asyncpg.exceptions.DuplicateObjectError'>: type "search_intent" already exists                                                          
  [SQL: CREATE TYPE search_intent AS ENUM ('informational', 'navigational', 'commercial', 'transactional')]                                
  (Background on this error at: https://sqlalche.me/e/20/f405)                                                                             
  (base) puneetha@puneetha-Latitude-7410:~/Documents/IterativeResearch/VIKAS/apps/api$                                                     

