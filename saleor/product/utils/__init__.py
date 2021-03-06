from urllib.parse import urlencode
import datetime

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.db.models import F

from ...cart.utils import (
    get_cart_from_request, get_or_create_cart_from_request)
from ...core.utils import get_paginator_items
from ...core.utils.filters import get_now_sorted_by
from ..forms import ProductForm
from .availability import products_with_availability
import random
from pdb import set_trace as bp


def products_visible_to_user(user):
    # pylint: disable=cyclic-import
    from ..models import Product
    if user.is_authenticated and user.is_active and user.is_staff:
        return Product.objects.all()
    return Product.objects.available_products()


def products_similar_to(product_id):
    # pylint: disable=cyclic-import
    from ..models import ProductSimilarity
    try:
        similar_products = ProductSimilarity.objects.get(product_id=product_id)
        return similar_products
    except ProductSimilarity.DoesNotExist:
        return None


def products_with_details(user, product_id=None):
    products = products_visible_to_user(user)
    if product_id is not None:
        product_similarity = products_similar_to(product_id)
        # HOTFIX: FIXING WHEN SIMILARITY NOT CALCULATED
        if product_similarity:
            similar_products = product_similarity.get_similar_products()
        else:
            similar_products = [product_id]
        clauses = ' '.join(['WHEN product_product.id=%s THEN %s' % (pk, i) 
            for i, pk in enumerate(similar_products)])
        ordering = 'CASE %s END' % clauses
        products = products.filter(pk__in=similar_products).extra(
            select={'ordering': ordering}, order_by=('ordering',))
    products = products.prefetch_related(
        'category', 'images', 'variants__variant_images__image',
        'attributes__values', 'product_type__product_attributes__values')
    return products


def products_for_homepage():
    user = AnonymousUser()
    products = products_with_details(user)
    products = products.filter(is_featured=True)
    return products


def get_product_images(product):
    """Return list of product images that will be placed in product gallery."""
    return list(product.images.all())


def handle_cart_form(request, product, create_cart=False):
    if create_cart:
        cart = get_or_create_cart_from_request(request)
    else:
        cart = get_cart_from_request(request)
    form = ProductForm(
        cart=cart, product=product, data=request.POST or None,
        discounts=request.discounts, taxes=request.taxes)
    return form, cart


def products_for_cart(user):
    products = products_visible_to_user(user)
    products = products.prefetch_related('variants__variant_images__image')
    return products


def get_variant_url_from_product(product, attributes):
    return '%s?%s' % (product.get_absolute_url(), urlencode(attributes))


def get_variant_url(variant):
    attributes = {
        str(attribute.pk): attribute
        for attribute in variant.product.product_type.variant_attributes.all()}
    return get_variant_url_from_product(variant.product, attributes)


def allocate_stock(variant, quantity):
    variant.quantity_allocated = F('quantity_allocated') + quantity
    variant.save(update_fields=['quantity_allocated'])


def deallocate_stock(variant, quantity):
    variant.quantity_allocated = F('quantity_allocated') - quantity
    variant.save(update_fields=['quantity_allocated'])


def decrease_stock(variant, quantity):
    variant.quantity = F('quantity') - quantity
    variant.quantity_allocated = F('quantity_allocated') - quantity
    variant.save(update_fields=['quantity', 'quantity_allocated'])


def increase_stock(variant, quantity, allocate=False):
    """Return given quantity of product to a stock."""
    variant.quantity = F('quantity') + quantity
    update_fields = ['quantity']
    if allocate:
        variant.quantity_allocated = F('quantity_allocated') + quantity
        update_fields.append('quantity_allocated')
    variant.save(update_fields=update_fields)


def get_product_list_context(request, filter_set, small_pagination=False):
    """
    :param request: request object
    :param filter_set: filter set for product list
    :return: context dictionary
    """
    # Avoiding circular dependency
    from ..filters import SORT_BY_FIELDS
    if small_pagination:
        paginate_by = settings.PAGINATE_BY_SMALL
    else:
        paginate_by = settings.PAGINATE_BY
    arg_sort_by = request.GET.get('sort_by')
    is_descending = arg_sort_by.startswith('-') if arg_sort_by else False
    products_paginated = get_paginator_items(
        filter_set.qs, paginate_by, request.GET.get('page'))
    products_and_availability = list(products_with_availability(
        products_paginated, request.discounts, request.taxes,
        request.currency))
    now_sorted_by = get_now_sorted_by(filter_set)
    return {
        'filter_set': filter_set,
        'products': products_and_availability,
        'products_paginated': products_paginated,
        'sort_by_choices': SORT_BY_FIELDS,
        'now_sorted_by': now_sorted_by,
        'is_descending': is_descending}


def collections_visible_to_user(user):
    # pylint: disable=cyclic-import
    from ..models import Collection
    if user.is_authenticated and user.is_active and user.is_staff:
        return Collection.objects.all()
    return Collection.objects.public()
