"""Generate a soft ambient/tension bed (no copyrighted music)."""
import numpy as np, wave
sr=44100; dur=70; t=np.arange(int(sr*dur))/sr
def note(f): return sum(np.sin(2*np.pi*f*k*t+k)/k**1.5 for k in (1,2,3))
chords=[[110,130.8,164.8,207.7],[98,123.5,146.8,185],[87.3,110,130.8,164.8],[82.4,103.8,123.5,155.6]]
out=np.zeros_like(t); seg=4.0
for i in range(int(dur/seg)+1):
    env=np.clip(1-np.abs((t-i*seg-seg/2)/(seg*0.75)),0,1)**1.5
    out+=env*sum(note(f) for f in chords[i%4])*0.08
pulse=(np.sin(2*np.pi*t*2)>0.95)*np.exp(-((t*2)%1)*18)*np.sin(2*np.pi*55*t)
out+=pulse*0.35
out=np.tanh(out*1.2)*0.6
fade=np.clip(t/1.5,0,1)*np.clip((dur-t)/2,0,1); out*=fade
st=np.stack([out,np.roll(out,300)],1)
w=wave.open('music.wav','wb'); w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr)
w.writeframes((st*32767).astype(np.int16).tobytes()); w.close()
