# Protocole

Transport : TCP. Messages de contrôle : un objet JSON par ligne, terminé par `\n`, encodé en UTF-8.
Chaque requête a un champ `type`. Chaque réponse a `ok` (true/false) et, en cas d'erreur, `error`.

## Hôte → serveur central (port 5000 par défaut)

| type      | champs envoyés                         | réponse si ok                 | erreurs possibles      |
|-----------|----------------------------------------|-------------------------------|------------------------|
| REGISTER  | user, salt, hash                       | {}                            | exists, bad_request    |
| CHALLENGE | user                                   | salt, nonce                   | unknown_user           |
| LOGIN     | user, proof                            | token                         | auth_failed            |
| PUBLISH   | token, host, port, files[]             | count                         | bad_token              |
| UPDATE    | token, files[]                         | count                         | bad_token              |
| SEARCH    | token, keyword, sort                   | items[]                       | bad_token              |
| HEARTBEAT | token                                  | {}                            | bad_token              |
| LOGOUT    | token                                  | {}                            | bad_token              |

- `hash` = PBKDF2-HMAC-SHA256(mot de passe, salt, 200 000 itérations), en hexadécimal.
- `proof` = HMAC-SHA256(clé = hash, message = nonce). Le mot de passe ne circule jamais.
- Un fichier dans `files[]` : `{name, desc, author, date, size, sha256}`. `name` est un chemin relatif.
- Un résultat dans `items[]` : `{user, host, port, name, desc, size, date}`.
- `sort` : `relevance` (défaut), `name`, `size`, `host`, `date`.

## Client → serveur de fichiers d'un hôte

| type | champs | réponse si ok                                       | erreurs     |
|------|--------|-----------------------------------------------------|-------------|
| GET  | name   | ligne JSON {size, sha256}, puis exactement size octets | not_found |

Aucune commande d'upload n'existe.

## Vie des hôtes
- HEARTBEAT toutes les 10 s.
- Le central retire un hôte de l'index après 30 s sans nouvelles, ou dès son LOGOUT.