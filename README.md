# higgsfield-video-agent

Agent de génération vidéo : vous décrivez la vidéo en une phrase, Claude rédige le prompt
cinématographique et choisit les réglages, puis l'[API Higgsfield](https://docs.higgsfield.ai)
(Kling 3.0 Turbo) produit le MP4. Il s'utilise en ligne de commande ou depuis l'onglet
**Actions** de GitHub.

## Installation

```bash
pip install -e .
```

Deux clés sont nécessaires, à placer dans l'environnement (voir `.env.example`) :

| Variable | Où l'obtenir |
| --- | --- |
| `HF_KEY` | [console.higgsfield.ai](https://console.higgsfield.ai), au format `key-id:key-secret` |
| `ANTHROPIC_API_KEY` | [platform.claude.com](https://platform.claude.com) (inutile avec `--direct`) |

## Utilisation

```bash
higgsfield-agent "Un renard roux traverse une forêt enneigée à l'aube, pour TikTok"
```

La vidéo est enregistrée dans `outputs/` et son URL est affichée (Higgsfield la conserve au
moins sept jours).

| Option | Effet |
| --- | --- |
| `--image <url ou fichier>` | part d'une image (image → vidéo) ; un fichier local est envoyé à Higgsfield |
| `--max-videos N` | plafond de générations facturées par exécution (2 par défaut) |
| `--direct` | sans Claude : le texte est envoyé tel quel, avec `--duration`, `--resolution`, `--aspect-ratio` |

Chaque génération consomme des crédits Higgsfield. Les générations échouées ou refusées par
la modération ne sont pas facturées.

## Depuis GitHub

1. Dans **Settings → Secrets and variables → Actions**, ajoutez les secrets `HF_KEY` et
   `ANTHROPIC_API_KEY`.
2. Dans **Actions → Generate video → Run workflow**, saisissez le brief.
3. Le résumé de l'exécution contient l'URL, et le MP4 est joint comme artefact `videos`.

## Changer de modèle

Les endpoints par défaut sont `kling-video/v3.0-turbo/text-to-video` et
`kling-video/v3.0-turbo/image-to-video`. Les variables `HIGGSFIELD_T2V_MODEL` et
`HIGGSFIELD_I2V_MODEL` permettent d'en choisir d'autres dans le
[catalogue](https://docs.higgsfield.ai/docs/models/video-generation), à condition qu'ils
acceptent les mêmes paramètres (`prompt`, `duration`, `resolution`, `aspect_ratio` / `image_url`).

## Tests

```bash
pip install -e ".[dev]"
pytest
```

Les tests n'appellent aucune API.
