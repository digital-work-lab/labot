# 🪄 LaBot: Facilitating work in the Digital-Work-Lab

```mermaid
graph LR
    labot[🪄 LaBot] --> cli["<a href='#cli'>CLI</a>"]
    labot --> ghactions["<a href='#github-actions'>GitHub Actions</a>"]
    cli --> status[Status]
    cli --> paper[Paper Management]
    cli --> thesis[Thesis Support]
    cli --> other_cli[...]
    ghactions --> repos[Update Repositories]
    ghactions --> thesis_stats[Thesis Stats]
    ghactions --> other_gha[...]
```

## CLI

Run the following command in the handbook directory:

```
labot status

```

Run these commands in an empty directory:

```
labot paper --init
labot thesis
```

## GitHub actions

Labot also runs as a GitHub action in different repositories (in the `labot.yaml`, which requires repo and workflow rights)
The entrypoint is `labot.repository.main()`.
