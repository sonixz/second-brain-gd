"""The assistant: talks with the user, works on the second brain through tools,
classifies every capture, writes the morning briefing and speaks it.

Principle: the assistant proposes and acts transparently. Every change it makes
is journaled in `assistant_actions` with the previous state and can be undone.
It uses the user's own OpenAI key (the same one as voice capture).
"""
