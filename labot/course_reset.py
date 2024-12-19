from pathlib import Path



def main():
    """Main function."""

    # replace all "- [x] " with "- [ ] " in the docs/* files
    docs_dir = "docs"
    for file in Path(docs_dir).glob("*"):
        if not file.is_file():
            continue
        with open(file) as f:
            contents = f.read()
        contents = contents.replace("- [x] ", "- [ ] ")
        with open(file, "w") as f:
            f.write(contents)


if __name__ == "__main__":
    main()
