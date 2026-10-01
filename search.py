from cli import main

if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as error:
        print(error)
        raise SystemExit(1) from error
