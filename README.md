# 🪄 LaBot: Facilitating work in the Digital-Work Lab

```mermaid
graph LR
    labot[🪄 LaBot] --> ghactions["<a href='?tab=readme-ov-file#github-actions'>GitHub Actions</a>"]
    labot --> cli["<a href='?tab=readme-ov-file#cli'>CLI</a>"]
    ghactions --> repos[Update Repositories]
    ghactions --> thesis_stats[Thesis Stats]
    ghactions --> other_gha[...]
    cli --> paper[Paper Management]
    cli --> thesis[Thesis Support]
    cli --> other_cli[...]
```

## CLI

Run these commands in an empty directory:

```
labot paper --init
labot thesis
```

Work-in-progress:

```
labot status
```

## GitHub actions

Labot also runs as a GitHub action in different repositories (in the `labot.yaml`, which requires repo and workflow rights)
The entrypoint is `labot.repository.main()`.
