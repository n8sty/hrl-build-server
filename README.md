# Getting started

Both branches to install Python dependencies assume you have Python 3.10 available
and SQLite. This project uses Poetry to manage it's dependencies. If you have Poetry
installed:

    poetry install

otherwise, a `requirements.txt` file has been included which can be used with a virtual
environment:

    python -m venv .venv
    sourve ./venv/bin/activate
    pip install -r requirements.txt

Create the projects database schema:

    cat schema.sql | sqlite3 db.sqlite

Run the project:

    poetry run uvicorn --reload hrlbs.server:create

and access it at http://127.0.0.1:8000/docs, which provides a browsable OpenAPI-defined
interface. The routes themselves should be self-explantory, though do lack documentation.

To register a program, assume that program has the assumed characteristics and is located
at the top-level of this project:

    curl -X 'POST' \
    'http://127.0.0.1:8000/program/register' \
    -H 'accept: application/json' \
    -H 'Content-Type: application/json' \
    -d '{
      "name": "hello",
      "source": "./hello"}'

Programs must be unique both by `name` and by `source`. The latter was an arbitrary decision
but the intention is that a program should only be register-able once. This is enforced via
database schema which can be found in `schema.sql`.

This will also work with references to Git repos that are not on the local file system, just
replace `source` with the appropriate reference.

To schedule a program, include `"build_schedule"; "@hourly"` key-value pair. The only option
is "hourly" for periodic builds.

To build a previously registered program:

    curl -X 'POST' \
      'http://127.0.0.1:8000/program/build' \
      -H 'accept: application/json' \
      -H 'Content-Type: application/json' \
      -d '{"program_name": "hello"}'

Take the `build_id` from the response above to retrieve the status of a build, for example:

    curl -X 'GET' \
    'http://127.0.0.1:8000/program/build/b0b8acb7-6c5c-4594-a51d-3233c9b1bdb3' \
    -H 'accept: application/json'

## Thoughts

Much of this is quite rough. There's a ton of duplicated code, which represents a way I think about doing things but isn't correct here. That way is that duplicating code, especially in the beginning of an idea or when a project is nascent is generally safer than trying to write reusable methods that may not actually be reusable and then instead require much handwringing.

There are definitely cases where if an error state is hit the server will get itself into a funny state. One notable one is that it's possible to clone down the repo in question while not successfully registering it as a record in the database. There's currently no way to fix this without manual intervention.

There are no tests! Obviously there should be...

The visualization part I'm fudging with the OpenAPI browsable API doc. This is part of the reason I like using FastAPI because this comes for free, and it's also a tool I've used before. I like the way validation is performed using Python's type tags and Pydantic modles (also uses `dataclasses` too).

I didn't container-ize this because of a lack of time. It then has the unfortunate effect of writing a bunch of files to your file system. Similar reason for using SQLite, it's lightweight, and has the added benefit of being quite good at storing blobs of bytes and texts, which is where the built artifact is ending up. The built artifact isn't being identified particularly well as it's assumed to be the most recently created file in the archive. That's ugly and will definitely break.

The `build` method is awful. In general, I don't like going through and using all these calls to system commands (ie: using `subprocess.Popen` and the like) but I didn't want to carry around GitPython to interface with Git as an added dependency. There are better ways to make system calls, but this is the one I'm most familiar with.

I didn't use any ORM because I find ORMs slow me down, especially in cases like this. Though, they have a lot of benefit in terms of schema management and helping cut down on boilerplate and encouraging reuse when working on a team.

There's definitely more that I'm overlooking, but that's it for now.
