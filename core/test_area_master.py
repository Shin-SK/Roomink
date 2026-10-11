from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Area, Room, Store, UserProfile


User = get_user_model()


class AreaMasterApiTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="エリアマスタ店")
        self.other_store = Store.objects.create(name="別エリアマスタ店")
        self.manager = User.objects.create_user("area_master_manager")
        self.staff = User.objects.create_user("area_master_staff")
        UserProfile.objects.create(user=self.manager, store=self.store, role=UserProfile.Role.MANAGER)
        UserProfile.objects.create(user=self.staff, store=self.store, role=UserProfile.Role.STAFF)
        self.client = APIClient()

    def as_user(self, user):
        self.client.force_authenticate(user)

    def test_manager_creates_normalized_unique_area_and_staff_cannot_change_it(self):
        self.as_user(self.manager)
        created = self.client.post("/api/areas/", {"name": " 高田馬場 "}, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data["name"], "高田馬場")
        duplicate = self.client.post("/api/areas/", {"name": "高田馬場"}, format="json")
        self.assertEqual(duplicate.status_code, 400, duplicate.data)
        self.as_user(self.staff)
        denied = self.client.post("/api/areas/", {"name": "新宿"}, format="json")
        self.assertEqual(denied.status_code, 403, denied.data)

    def test_room_cannot_reference_another_store_area(self):
        foreign_area = Area.objects.create(store=self.other_store, name="他店舗エリア")
        room = Room.objects.create(store=self.store, name="101")
        self.as_user(self.manager)
        response = self.client.patch(f"/api/rooms/{room.id}/", {"area": foreign_area.id}, format="json")
        self.assertEqual(response.status_code, 400, response.data)
