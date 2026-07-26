# apps/branches/models.py

# Create your models here.
from django.db import models


class Branch(models.Model):
    name = models.CharField(
        max_length=100, 
        unique=True, 
        help_text="Unique name of the physical branch location."
    )
    location = models.CharField(
        max_length=255, 
        help_text="Physical physical address or landmark details."
    )
    is_active = models.BooleanField(
        default=True, 
        help_text="Designates whether this branch is currently operational."
    )
    receives_supplier_stock = models.BooleanField(
        default=False,
        help_text=(
            "Allows supplier deliveries to be booked directly into this branch. "
            "For the current business, this should be enabled only for the OTC hub."
        ),
    )
    offers_customer_pickup = models.BooleanField(
        default=False,
        db_index=True,
        help_text=(
            "Allows customers to select this branch as a collection point. "
            "For the current business, this should be enabled only for S18."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Branch"
        verbose_name_plural = "Branches"
        ordering = ['name']

    def __str__(self):
        return self.name
