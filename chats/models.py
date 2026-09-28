from django.db import models


class Category(models.Model):
    """Categoria dell'archivio. Le categorie di primo livello sono le aree
    (Villa Franciacorta, NARPI, AROMA, Emozione, Personale...), quelle di
    secondo livello le sottocategorie (es. Personale > Finanza personale)."""

    name = models.CharField("nome", max_length=120)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE,
        related_name="children", verbose_name="area",
    )
    keywords = models.TextField(
        "parole chiave", blank=True,
        help_text="Una per riga. Usate dalla classificazione automatica.",
    )
    order = models.PositiveIntegerField("ordine", default=0)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "categoria"
        verbose_name_plural = "categorie"
        constraints = [
            models.UniqueConstraint(fields=["parent", "name"], name="uniq_category_name"),
        ]

    def __str__(self):
        return f"{self.parent.name} › {self.name}" if self.parent_id else self.name

    @property
    def full_name(self):
        return str(self)

    def keyword_list(self):
        return [k.strip().lower() for k in self.keywords.splitlines() if k.strip()]

    def descendant_ids(self):
        return [self.id] + list(self.children.values_list("id", flat=True))


class Project(models.Model):
    """Progetto di ChatGPT (gizmo 'g-p-...'). Il nome si può correggere
    dall'interfaccia; la categoria predefinita si applica alle sue chat."""

    external_id = models.CharField(max_length=80, unique=True)
    name = models.CharField("nome", max_length=200)
    default_category = models.ForeignKey(
        Category, null=True, blank=True, on_delete=models.SET_NULL,
        verbose_name="categoria predefinita",
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "progetto"
        verbose_name_plural = "progetti"

    def __str__(self):
        return self.name


class Conversation(models.Model):
    SOURCES = [("chatgpt", "ChatGPT"), ("claude", "Claude")]
    ASSIGNED_BY = [
        ("", "non assegnata"),
        ("auto", "automatica"),
        ("project", "da progetto"),
        ("manual", "manuale"),
    ]

    source = models.CharField(max_length=20, choices=SOURCES, default="chatgpt")
    external_id = models.CharField(max_length=80)
    title = models.CharField("titolo", max_length=500)
    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)
    model_slug = models.CharField(max_length=80, blank=True)
    url = models.URLField(max_length=300, blank=True)
    folder = models.CharField(
        max_length=300, blank=True,
        help_text="Cartella dell'export (relativa alla radice dell'export).",
    )
    project = models.ForeignKey(
        Project, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="conversations",
    )
    category = models.ForeignKey(
        Category, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="conversations", verbose_name="categoria",
    )
    assigned_by = models.CharField(max_length=10, choices=ASSIGNED_BY, blank=True, default="")
    message_count = models.PositiveIntegerField(default=0)
    attachment_count = models.PositiveIntegerField(default=0)
    excerpt = models.TextField(blank=True, help_text="Inizio della prima domanda.")
    source_mtime = models.FloatField(default=0)
    notes = models.TextField("note", blank=True)
    archived = models.BooleanField("archiviata", default=False, db_index=True)
    remote_deleted_at = models.DateTimeField(
        "eliminata su ChatGPT il", null=True, blank=True,
        help_text="Impostato dal comando elimina_su_chatgpt.",
    )

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(fields=["source", "external_id"], name="uniq_conversation"),
        ]
        indexes = [models.Index(fields=["category", "-updated_at"])]
        verbose_name = "conversazione"
        verbose_name_plural = "conversazioni"

    def __str__(self):
        return self.title

    @property
    def is_manual(self):
        return self.assigned_by == "manual"


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    position = models.PositiveIntegerField()
    role = models.CharField(max_length=20)
    kind = models.CharField(
        max_length=20, default="text",
        help_text="text, code, output, thoughts, recap, quote, tool",
    )
    author_name = models.CharField(max_length=80, blank=True)
    language = models.CharField(max_length=40, blank=True)
    text = models.TextField()
    created_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["position"]
        indexes = [models.Index(fields=["conversation", "position"])]


class Attachment(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="attachments")
    name = models.CharField(max_length=300)
    path = models.CharField(max_length=500, help_text="Relativo alla radice dell'export.")
    size = models.PositiveBigIntegerField(default=0)

    class Meta:
        ordering = ["name"]

    @property
    def is_image(self):
        return self.name.lower().rsplit(".", 1)[-1] in {"png", "jpg", "jpeg", "gif", "webp"}
