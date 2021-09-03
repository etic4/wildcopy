#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import subprocess
import shlex

import logging
from logging import Logger
from logging.handlers import RotatingFileHandler


def get_logger(name: str, str_loglevel: str="INFO", file: bool=False) -> logging.Logger:
    """configuration du logging. Par défaut, streamhandler au niveau INFO. Si file == True, configure un filehandler au même niveau de nom 'name'
    """
    loglevel: int = getattr(logging, str_loglevel)

    logger = logging.getLogger(name)
    logger.setLevel(loglevel)
    console_logger = logging.StreamHandler()
    console_logger.setLevel(loglevel)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_logger.setFormatter(formatter)
    logger.addHandler(console_logger)

    if file:
        file_logger = RotatingFileHandler("{}.log".format(name), maxBytes=10**7, backupCount=3)
        file_logger.setLevel(loglevel)
        file_logger.setFormatter(formatter)
        logger.addHandler(file_logger)

    return logger


def running_as_root() -> bool:
    """Check si lancé en tant que root
    """
    euid = os.geteuid()

    if euid != 0:
        return False

    return True


def sudo_exec_as_normal_user(orig_cmd: str) -> None:
    """Exécuter un commande comme utilisateur normal quand sudo (sinon exécuté avec la user id courante)
    """
    sudo_user = os.environ.get("SUDO_USER", None)

    if sudo_user:
        cmd = "su {} -c '{}'".format(sudo_user, orig_cmd)
    else:
        cmd = orig_cmd

    subprocess.run(shlex.split(cmd))


if __name__ == "__main__":
    logger = get_logger("test")
    logger.info("Test info")
    logger.error("Test error")
