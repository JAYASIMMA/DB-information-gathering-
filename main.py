import sys

if "--store-all" in sys.argv or "--store" in sys.argv:
    # pyrefly: ignore [missing-import]
    from store_all_dbs_to_e34data78 import main as store_main
    store_main()
else:
    # pyrefly: ignore [missing-import]
    from src.inspector import main
    main()
