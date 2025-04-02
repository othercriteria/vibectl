"""
Prompt templates for LLM interactions
"""

GET_RESOURCE_PROMPT = """Summarize this kubectl output focusing on key information,
notable patterns, and potential issues.

Be direct and concise - skip any introductory phrases like "This output shows"
or "I can see".

Format your response using rich.Console() markup syntax with matched closing tags:
- [bold]resource names and counts[/bold] for emphasis
- [green]healthy/good status[/green] for positive states
- [yellow]warnings or potential issues[/yellow] for concerning states
- [red]errors or critical issues[/red] for problems
- [blue]namespaces and other Kubernetes concepts[/blue] for k8s terms
- [italic]additional context or timing information[/italic] for metadata

Example format:
[bold]3 pods[/bold] in [blue]default namespace[/blue], all [green]Running[/green].
[bold]nginx-pod[/bold] [italic]running for 2 days[/italic].
[yellow]Warning: 2 pods have high restart counts[/yellow].

Here's the output:

{output}"""
