from django.urls import path

from . import views

app_name = 'igportal'

urlpatterns = [
    path('', views.panel, name='panel'),
    path('publicaciones/', views.publicaciones, name='publicaciones'),
    path('publicaciones/nueva/', views.publicacion_form, name='nueva'),
    path('publicaciones/<int:pub_id>/editar/', views.publicacion_form, name='editar'),
    path('publicaciones/<int:pub_id>/publicar/', views.publicar, name='publicar'),
    path('publicaciones/<int:pub_id>/verificar/', views.verificar, name='verificar'),
    path('publicaciones/<int:pub_id>/cancelar/', views.cancelar, name='cancelar'),
    path('publicaciones/<int:pub_id>/eliminar/', views.eliminar, name='eliminar'),
    path('comentarios/<str:media_id>/', views.comentarios, name='comentarios'),
    path('conexion/', views.conexion, name='conexion'),
]
