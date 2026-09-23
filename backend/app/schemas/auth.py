from pydantic import BaseModel, ConfigDict, model_validator


class LoginRequest(BaseModel):
    username: str
    password: str

    @model_validator(mode="after")
    def validate_credentials(self):
        if not self.username.strip():
            raise ValueError("Username is required.")
        if not self.password:
            raise ValueError("Password is required.")
        return self


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    role: str
