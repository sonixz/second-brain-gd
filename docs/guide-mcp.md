# Connect Claude Code to your Brain (MCP) · Brancher Claude Code sur ton Brain

**FR.** Ton Brain peut servir de serveur MCP : Claude Code (ou un autre outil MCP) le lit et y cherche, sur cet
ordinateur seulement. Il n'écrit jamais directement : ce qu'il propose passe par l'archiviste (prochaine étape).

1. Dans la barre du haut, clique les voyants **⇠● ⇢●** (à côté de « Tout fonctionne »).
2. Donne un nom (« Claude Code ») et clique **Brancher un outil d'IA (lecture)**.
3. Copie **une** des deux commandes (la clé n'est montrée qu'une fois) :
   - Claude Code sous Windows : `claude mcp add --transport http second-brain http://127.0.0.1:<port>/mcp --header "Authorization: Bearer …"`
   - Claude Code dans WSL : `claude mcp add second-brain -- "/mnt/c/Users/<toi>/AppData/Local/SecondBrainGD/.venv/Scripts/python.exe" "C:\…\engine\mcp\relay.py" --client <id>`
     (un petit relais lancé avec le Python de l'app ; aucun réglage réseau, aucun droit admin)
4. Relance Claude Code (une session voit les nouveaux serveurs MCP à son démarrage), puis demande-lui par exemple
   « qu'est-ce que j'ai dans mon Brain sur la cuisine ? ».
5. Le voyant **⇠** devient vert quand un outil est branché, et rouge pendant un appel. **Débrancher** révoque sa clé.

Outils offerts : `overview`, `search`, `get_item`, `list_places`, `list_items`, `neighbours`, `path`, `recent`,
`inbox`, `item_types`, `table`. Les réponses sont courtes et par pages ; le contenu du Brain est toujours marqué comme
des données, jamais comme des consignes.

**EN.** Your Brain can be an MCP server: Claude Code (or any MCP client) reads and searches it, on this computer
only. It never writes directly; proposals go through the archivist (next step). Click the **⇠● ⇢●** lights in the
top bar, name the tool, **Connect an AI tool (read)**, copy one command (the key is shown once), restart Claude
Code. **⇠** turns green when a tool is connected and red during a call; **Disconnect** revokes its key.

## Les serveurs MCP pour tes agents (⇢ sortant) · MCP servers for your agents

**FR.** Dans la même fenêtre, **+ Brancher Microsoft Learn** (public, gratuit, sans compte) donne à tes agents la
recherche dans la documentation Microsoft et Azure, les exemples de code et la lecture d'une page. Choisis **Tous les
agents** ou **Seulement** un agent. Le voyant **⇢** devient vert quand un serveur est prêt, rouge pendant un appel.
Ce qu'un serveur renvoie est traité comme une page web : de l'information, jamais des consignes. Les réponses
coûtent des jetons (environ quelques cents par question avec le modèle par défaut).

**EN.** In the same window, **+ Connect Microsoft Learn** gives your agents Microsoft and Azure documentation search,
code samples and page reading. Choose **All agents** or **Only** one. **⇢** turns green when a server is ready, red
during a call. What a server returns is information, never instructions.
