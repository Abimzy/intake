import factory
from intake import models


class StatusNotificationFactory(factory.DjangoModelFactory):
    status_update = factory.Iterator(models.StatusUpdate.objects.all())
    contact_info = {"email": "bgolder+borg@codeforamerica.org"}
    base_message = "Resistance is futile"
    sent_message = "Live long and prosper"

    class Meta:
        model = models.StatusNotification
