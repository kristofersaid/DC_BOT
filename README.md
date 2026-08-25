# DC_BOT

Narzędzie dla Windows do pobierania załączników graficznych z kanałów Discorda.
Aplikacja posiada graficzny interfejs użytkownika oparty na Tkinterze i zapisuje
pobrane pliki w katalogu `OUTPUT/`.

## Funkcje

- pobieranie plików z wybranego kanału Discorda,
- tryby pobierania: ostatnie pliki, od wybranej daty, zakres dat oraz tygodnie,
- podgląd pobranych obrazów w GUI,
- konwersja obsługiwanych obrazów do PNG,
- narzędzie do ponownego przetwarzania plików w `OUTPUT/`.

## Wymagania

- Windows,
- Python 3.10 lub nowszy,
- konto Discord z dostępem do kanału, z którego mają być pobierane pliki.

## Instalacja z venv

1. Sklonuj repozytorium i przejdź do katalogu projektu:

	```powershell
	git clone https://github.com/kristofersaid/DC_BOT.git
	cd DC_BOT
	```

2. Utwórz i aktywuj środowisko wirtualne:

	```powershell
	py -m venv venv
	.\venv\Scripts\Activate.ps1
	```

	Jeśli PowerShell blokuje aktywację skryptów, uruchom jednorazowo:

	```powershell
	Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
	```

3. Zainstaluj zależności:

	```powershell
	python -m pip install --upgrade pip
	pip install -r requirements.txt
	```

Po instalacji środowisko `venv` pozostaje aktywne w bieżącym terminalu. Przy
kolejnym uruchomieniu projektu przejdź do jego katalogu i ponownie aktywuj je:

```powershell
cd DC_BOT
.\venv\Scripts\Activate.ps1
```

## Konfiguracja

Utwórz w katalogu projektu plik `main_config.json`:

```json
{
	 "token": "TWÓJ_TOKEN_DISCORDA",
	 "channel_link": "https://discord.com/channels/SERVER_ID/CHANNEL_ID",
	 "limit": 1000
}
```

Token jest przechowywany lokalnie. Plik `main_config.json` jest celowo wykluczony
z repozytorium przez `.gitignore` i nie powinien być publikowany ani udostępniany.
Nie używaj tokena innej osoby i nie umieszczaj go w kodzie źródłowym.

## Uruchamianie

Po aktywacji środowiska wirtualnego uruchom GUI:

```powershell
python dc_bot_gui.py
```

Możesz też uruchomić `dc_bot_start.bat`, który korzysta z interpretera z katalogu
`venv/`. Token i link do kanału można zaktualizować z poziomu aplikacji.

Skrypt konwersji obrazów można uruchomić osobno:

```powershell
python dc_cleanup_images.py
```

Pobrane pliki trafiają do podkatalogów `OUTPUT/`. Ten katalog jest lokalnym
artefaktem pracy i nie jest wysyłany do repozytorium.

## Zasady bezpieczeństwa

Token Discorda jest poświadczeniem dostępu. Jeśli token został ujawniony,
natychmiast go unieważnij i wygeneruj nowy. Pobieraj materiały wyłącznie z
kanałów, do których masz uprawnienia, i przestrzegaj regulaminu Discorda oraz
praw autorskich.

## Usuwanie projektu

Aby usunąć projekt, wystarczy usunąć cały folder `DC_BOT`. Usunięte zostaną
również środowisko `venv`, lokalna konfiguracja `main_config.json` oraz pobrane
pliki z katalogu `OUTPUT/`.
