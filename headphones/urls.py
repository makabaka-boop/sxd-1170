from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from . import views


router = DefaultRouter()
router.register(r'batches', views.BatchViewSet)
router.register(r'boxes', views.BoxViewSet)
router.register(r'headphones', views.HeadphoneViewSet)
router.register(r'borrow-records', views.BorrowRecordViewSet)
router.register(r'disinfection-records', views.DisinfectionRecordViewSet)
router.register(r'review-records', views.ReviewRecordViewSet)
router.register(r'abnormal-records', views.AbnormalRecordViewSet)
router.register(r'extension-applies', views.ExtensionApplyViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('auth/login/', views.login_view, name='login'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/me/', views.current_user_view, name='current_user'),
    path('action/<str:action_type>/', views.HeadphoneActionView.as_view(), name='headphone_action'),
    path('statistics/', views.statistics_view, name='statistics'),
    path('abnormal-detection/', views.abnormal_detection_view, name='abnormal_detection'),
]
