from django.contrib import admin

from .models import Category, Conversation, Project


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("__str__", "order")
    list_filter = ("parent",)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "external_id", "default_category")


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("title", "updated_at", "category", "assigned_by", "message_count")
    list_filter = ("assigned_by", "category", "source")
    search_fields = ("title", "external_id")
    raw_id_fields = ("category", "project")
