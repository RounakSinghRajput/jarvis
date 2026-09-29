import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("jarvis")

def main() -> None:
    logger.info("JARVIS is alive")

if __name__ == "__main__":
    main()