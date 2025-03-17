from django import forms
from .models import PetPreference

class PetPreferenceForm(forms.ModelForm):
    class Meta:
        model = PetPreference
        fields = ['pet_name', 'pet_position', 'pet_size', 'enabled']
        widgets = {
            'pet_name': forms.TextInput(attrs={'class': 'form-control'}),
            'pet_position': forms.Select(attrs={'class': 'form-select'}),
            'pet_size': forms.Select(attrs={'class': 'form-select'}),
            'enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'})
        }
        help_texts = {
            'pet_name': 'Give your virtual pet a unique name',
            'pet_position': 'Where on the screen your pet will appear',
            'pet_size': 'How big your pet will be',
            'enabled': 'Turn your pet on or off'
        }
        
    def clean_pet_name(self):
        name = self.cleaned_data.get('pet_name')
        if name and len(name) < 2:
            raise forms.ValidationError("Pet name must be at least 2 characters long")
        return name