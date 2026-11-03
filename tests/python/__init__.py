"""Test isolation: never reach the user's real OpenAI key.

The engine looks for the key in the OS keyring (service SecondBrainGD), then in
OPENAI_API_KEY. Tests use a separate keyring service and drop the variable, so
engines started by the tests (and their background meaning worker) never call
the real API or spend the user's credit. Tests that need a key set their own.
"""
import os

os.environ["SBGD_KEYRING_SERVICE"] = "SecondBrainGD-test"
os.environ.pop("OPENAI_API_KEY", None)
