import subprocess
import sys


def run_tests(file):
    subprocess.run(["pytest", "-q", file])


if __name__ == "__main__":
    run_tests(sys.argv[1])