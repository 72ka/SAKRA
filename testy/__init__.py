import os
import tempfile

os.environ.setdefault("SAKRA_CACHE", "0")      # testy nepíší do mezipaměti uživatele (viz test_mezipamet)
# ani do jeho nastavení (profily, složky, vzhled): vlastní soubor INI pro celý běh testů
os.environ.setdefault("SAKRA_NASTAVENI", os.path.join(tempfile.mkdtemp(prefix="sakra-test-"), "sakra.ini"))
