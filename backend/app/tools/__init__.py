from .shopping_tools import (
    get_fridge_inventory, add_to_shopping_list,
    compare_supermarket_prices, generate_shopping_list,
    search_product_prices
)
from .recipe_tools import (
    search_recipes, get_recipe_detail,
    generate_meal_plan, match_recipes_by_ingredients
)
from .appliance_tools import (
    get_appliance_status, schedule_appliance,
    generate_off_peak_schedule, control_smart_appliance
)
from .maintenance_tools import (
    check_maintenance_due, create_maintenance_task,
    find_service_contact, send_maintenance_reminder
)
from .notification_tools import (
    send_notification, send_bill_reminder,
    format_notification_message
)
from .calendar_tools import (
    get_weekly_schedule, add_calendar_event,
    find_free_time_slots, schedule_task
)

__all__ = [
    # Shopping
    "get_fridge_inventory", "add_to_shopping_list",
    "compare_supermarket_prices", "generate_shopping_list",
    "search_product_prices",
    # Recipes
    "search_recipes", "get_recipe_detail",
    "generate_meal_plan", "match_recipes_by_ingredients",
    # Appliances
    "get_appliance_status", "schedule_appliance",
    "generate_off_peak_schedule", "control_smart_appliance",
    # Maintenance
    "check_maintenance_due", "create_maintenance_task",
    "find_service_contact", "send_maintenance_reminder",
    # Notifications
    "send_notification", "send_bill_reminder",
    "format_notification_message",
    # Calendar
    "get_weekly_schedule", "add_calendar_event",
    "find_free_time_slots", "schedule_task",
]
