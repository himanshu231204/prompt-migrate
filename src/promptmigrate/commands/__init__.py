"""One module per CLI verb.

Each module holds the verb's use-case function (re-exported by promptmigrate.core) and `run(args)`, which cli.py
dispatches to and which prints the verb's text output.
"""
