# LaBot: Facilitating work in the Digital-Work Lab

## CLI

Run these commands in an empty directory:

```
# In an empty repository:
labot paper --init
labot paper --prep

labot thesis --submissions
labot thesis --register
labot thesis --grade

labot references consolidate paper.pdf --mailto g.wagner@fs.de

labot notes
```

Work-in-progress:

```
labot status
```

For local tests with chatgpt (at the end of ./.bashrc):

```
export OPENAI_KEY="your_openai_api_key"
expport GITHUB_TOKEN="your_pat_token"
expport LABOT_PAT_TOKEN="labot_pat_token"
```

To test the repos a token has access to:

```
curl -H "Authorization: token <your_token>" https://api.github.com/user/repos
```

## GitHub actions

Labot also runs as a GitHub action in different repositories (in the `labot.yaml`, which requires repo and workflow rights)
The entrypoint is [`labot.repository.main()`](labot/repository.py).

**Paper repository**

- Checks `paper.md`, uses colrev-sync to update references

https://llmstxt.org/
https://llmstxt.org/intro.html
