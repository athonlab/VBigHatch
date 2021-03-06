
from south.db import db
from django.db import models
from mysite.search.models import *

class Migration:
    
    def forwards(self, orm):
        
        # Adding field 'Bug.date_reported'
        db.add_column('search_bug', 'date_reported', models.DateField())
        
    
    
    def backwards(self, orm):
        
        # Deleting field 'Bug.date_reported'
        db.delete_column('search_bug', 'date_reported')
        
    
    
    models = {
        'search.project': {
            'icon_url': ('models.URLField', [], {'max_length': '200'}),
            'id': ('models.AutoField', [], {'primary_key': 'True'}),
            'language': ('models.CharField', [], {'max_length': '200'}),
            'name': ('models.CharField', [], {'max_length': '200'})
        },
        'search.bug': {
            'date_reported': ('models.DateField', [], {}),
            'description': ('models.TextField', [], {}),
            'id': ('models.AutoField', [], {'primary_key': 'True'}),
            'importance': ('models.CharField', [], {'max_length': '200'}),
            'last_polled': ('models.DateField', [], {}),
            'last_touched': ('models.DateField', [], {}),
            'people_involved': ('models.IntegerField', [], {}),
            'project': ('models.ForeignKey', ['Project'], {}),
            'status': ('models.CharField', [], {'max_length': '200'}),
            'submitter_realname': ('models.CharField', [], {'max_length': '200'}),
            'submitter_username': ('models.CharField', [], {'max_length': '200'}),
            'title': ('models.CharField', [], {'max_length': '200'})
        }
    }
    
    complete_apps = ['search']
