/**
 * The student's profile photo. Picked from the library or taken with the camera, cropped square, then copied into
 * the app's document folder (the picker's own copy is in a cache the system may clear) and remembered in the prefs.
 * It stays on the phone; nothing uploads it.
 */
import * as ImagePicker from "expo-image-picker";
import { File, Paths } from "expo-file-system";
import { Platform } from "react-native";
import { getPrefs, setPrefs } from "./app";

export type PhotoSource = "camera" | "library";
export type PhotoResult = "set" | "cancelled" | "denied" | "unavailable";

function deleteQuietly(uri: string | null) {
  if (!uri || Platform.OS === "web") return;
  try {
    const file = new File(uri);
    if (file.exists) file.delete();
  } catch {
    /* already gone */
  }
}

export async function pickProfilePhoto(source: PhotoSource): Promise<PhotoResult> {
  try {
    if (source === "camera") {
      const permission = await ImagePicker.requestCameraPermissionsAsync();
      if (!permission.granted) return "denied";
    }
    const options: ImagePicker.ImagePickerOptions = { mediaTypes: ["images"], allowsEditing: true, aspect: [1, 1], quality: 0.6 };
    const result = source === "camera" ? await ImagePicker.launchCameraAsync(options) : await ImagePicker.launchImageLibraryAsync(options);
    if (result.canceled) return "cancelled";

    const picked = result.assets[0].uri;
    let uri = picked;
    if (Platform.OS !== "web") {
      // a new name each time, so the avatar re-renders instead of showing the old image from cache
      const kept = new File(Paths.document, `profile-${Date.now()}.jpg`);
      await new File(picked).copy(kept);
      uri = kept.uri;
    }
    deleteQuietly(getPrefs().photoUri);
    setPrefs({ photoUri: uri });
    return "set";
  } catch {
    // no camera (the simulator), or the picker could not open
    return "unavailable";
  }
}

export function removeProfilePhoto(): void {
  deleteQuietly(getPrefs().photoUri);
  setPrefs({ photoUri: null });
}
