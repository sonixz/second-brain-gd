# Connect an AI tool to your Brain (MCP) · Brancher un outil d'IA sur ton Brain

**FR.** Ton Brain est un serveur MCP standard : tout outil d'IA qui parle MCP le lit et y cherche, sur cet ordinateur
seulement (127.0.0.1) : Claude Code, Codex, GitHub Copilot dans VS Code (mode agent), Cursor, Claude Desktop… Il
n'écrit jamais directement : ce qu'il propose passe par l'archiviste (prochaine étape).

1. Dans la barre du haut, clique les voyants **⇠● ⇢●** (ou **⚙ → Outils d'IA**), onglet **Qui peut lire ton Brain**.
2. Choisis ton outil et clique **Brancher (lecture seule)**.
3. Copie ce qui s'affiche (la clé n'est montrée qu'une fois) :
   - Claude Code sous Windows : `claude mcp add --transport http second-brain http://127.0.0.1:<port>/mcp --header "Authorization: Bearer …"`
   - Claude Code ou Codex dans WSL : `claude mcp add second-brain -- "/mnt/c/Users/<toi>/AppData/Local/SecondBrainGD/.venv/Scripts/python.exe" "C:\…\engine\mcp\relay.py" --client <id>`
     (même chose avec `codex mcp add` ; un petit relais lancé avec le Python de l'app, aucun réglage réseau, aucun droit admin)
   - Codex sous Windows : `codex mcp add second-brain -- "C:\…\python.exe" "C:\…\engine\mcp\relay.py" --client <id>`
   - VS Code (Copilot en mode agent) : les lignes à coller dans `mcp.json` (`"type": "http"`, l'adresse et l'en-tête)
   - Cursor : les lignes à coller dans `~/.cursor/mcp.json`
   - Un autre client MCP : l'adresse `http://127.0.0.1:<port>/mcp` (Streamable HTTP) et l'en-tête
     `Authorization: Bearer …`, ou la commande du relais (stdio)
4. Relance l'outil (il voit les nouveaux serveurs MCP à son démarrage), puis demande-lui par exemple
   « qu'est-ce que j'ai dans mon Brain sur la cuisine ? ».
5. Le voyant **⇠** devient vert quand un outil est branché, et rouge pendant un appel. **Débrancher** révoque sa clé.

Outils offerts : `overview`, `search`, `get_item`, `list_places`, `list_items`, `neighbours`, `path`, `recent`,
`inbox`, `item_types`, `table`. Les réponses sont courtes et par pages ; le contenu du Brain est toujours marqué comme
des données, jamais comme des consignes.

**EN.** Your Brain is a standard MCP server: any AI tool that speaks MCP reads and searches it, on this computer
only (127.0.0.1): Claude Code, Codex, GitHub Copilot in VS Code (agent mode), Cursor, Claude Desktop… It never writes
directly; proposals go through the archivist (next step). Click the **⇠● ⇢●** lights in the top bar (or
**⚙ → AI tools**), first tab **Who may read your Brain**, pick your tool, **Connect (read only)**, copy its command or
settings (the key is shown once), restart the tool. **⇠** turns green when a tool is connected and red during a call;
**Disconnect** revokes its key.

## Les serveurs MCP pour tes agents (⇢ sortant) · MCP servers for your agents

**FR.** Dans la même fenêtre, onglet **Outils de tes agents**, sous **Ajouter un outil** : un des serveurs proposés (vérifiés à la main, sans compte), une recherche dans le registre
MCP officiel, ou l'adresse d'un serveur. Ses outils deviennent ceux de tes agents (documentation, code, recherche web,
tes autres applications). Choisis **Tous les
agents** ou **Seulement** un agent. Le voyant **⇢** devient vert quand un serveur est prêt, rouge pendant un appel.
Ce qu'un serveur renvoie est traité comme une page web : de l'information, jamais des consignes. Les réponses
coûtent des jetons (environ quelques cents par question avec le modèle par défaut).

**EN.** In the same window, tab **Tools for your agents**, under **Add a tool**: one of the starters (checked by hand, no account), a search in the official MCP registry, or a
server's address. Its tools become your agents' tools (documentation, code, web search, your other apps). Choose **All agents** or **Only** one. **⇢** turns green when a server is ready, red
during a call. What a server returns is information, never instructions.
