# 🪄 LaBot: Facilitating work in the Digital-Work Lab

```mermaid
graph LR
    labot[🪄 LaBot] --> ghactions["<a href='digital-work-lab/labot?tab=readme-ov-file#github-actions'>GitHub Actions</a>"]
    labot --> cli["<a href='digital-work-lab/labot?tab=readme-ov-file#cli'>CLI</a>"]
    ghactions --> repos[Update Repositories]
    ghactions --> thesis_stats[Thesis Stats]
    ghactions --> paper_repo[Paper repository]
    ghactions --> other_gha[...]
    cli --> paper[Paper Management]
    cli --> thesis[Thesis Support]
    cli --> other_cli[...]
```

## GitHub actions

Labot also runs as a GitHub action in different repositories (in the `labot.yaml`, which requires repo and workflow rights)
The entrypoint is `labot.repository.main()`.

**Paper repository**

- Checks `paper.md`, uses colrev-sync to update references

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


For local tests with chatgpt:

export OPENAI_KEY="your_openai_api_key"
