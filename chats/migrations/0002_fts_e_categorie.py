from django.db import migrations

SEED = [
    ("Villa Franciacorta", ["villa franciacorta", "franciacorta", "cantina", "vendemmia",
                            "vigneto", "vigneti", "unadì", "unadi", "vfpm", "consortium"]),
    ("NARPI", ["narpi"]),
    ("AROMA", ["aroma"]),
    ("Emozione", ["emozione"]),
    ("Tecnologia e IT", []),
    ("Personale", []),
]
PERSONAL = [
    ("Finanza personale", []),
    ("Viaggi", []),
    ("Sport", []),
    ("Acquisti", []),
]


def fts(apps, schema_editor):
    try:
        schema_editor.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS chats_conversation_fts USING fts5("
            "title, body, tokenize='unicode61 remove_diacritics 2')")
    except Exception as e:  # SQLite senza FTS5: la ricerca userà il ripiego LIKE
        print(f"\n  ! FTS5 non disponibile ({e}); ricerca in modalità semplice.")


def no_fts(apps, schema_editor):
    schema_editor.execute("DROP TABLE IF EXISTS chats_conversation_fts")


def seed(apps, schema_editor):
    Category = apps.get_model("chats", "Category")
    if Category.objects.exists():
        return
    for i, (name, kws) in enumerate(SEED):
        Category.objects.create(name=name, keywords="\n".join(kws), order=i)
    personal = Category.objects.get(name="Personale", parent=None)
    for i, (name, kws) in enumerate(PERSONAL):
        Category.objects.create(name=name, parent=personal, keywords="\n".join(kws), order=i)


class Migration(migrations.Migration):
    dependencies = [("chats", "0001_initial")]
    operations = [
        migrations.RunPython(fts, no_fts),
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
