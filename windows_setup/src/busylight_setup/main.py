import multiprocessing as mp

from busylight_setup.app import SetupWizard


def main() -> None:
    mp.freeze_support()
    app = SetupWizard()
    app.mainloop()


if __name__ == "__main__":
    main()
